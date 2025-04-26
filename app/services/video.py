import glob
import os
import random
import traceback
import subprocess
import gc
from typing import List

import psutil
from loguru import logger
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    afx,
    concatenate_videoclips,
)
from moviepy.video.tools.subtitles import SubtitlesClip
from PIL import ImageFont

from app.models import const
from app.models.schema import (
    MaterialInfo,
    VideoAspect,
    VideoConcatMode,
    VideoParams,
    VideoTransitionMode,
)
from app.services.utils import video_effects
from app.utils import utils
from app.config import config


def get_bgm_file(bgm_type: str = "random", bgm_file: str = ""):
    if not bgm_type:
        return ""

    if bgm_file and os.path.exists(bgm_file):
        return bgm_file

    if bgm_type == "random":
        suffix = "*.mp3"
        song_dir = utils.song_dir()
        files = glob.glob(os.path.join(song_dir, suffix))
        return random.choice(files)

    return ""


def kill_ffmpeg_processes():
    try:
        if os.name == 'nt':  # Windows
            subprocess.run(['taskkill', '/F', '/IM', 'ffmpeg.exe'], capture_output=True)
        else:  # Linux/Mac
            subprocess.run(['pkill', 'ffmpeg'], capture_output=True)
        logger.info("Killed all remaining ffmpeg processes")
    except Exception as e:
        logger.error(f"Error killing ffmpeg processes: {str(e)}")


def combine_videos(
    combined_video_path: str,
    video_paths: List[str],
    audio_file: str,
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_concat_mode: VideoConcatMode = VideoConcatMode.random,
    video_transition_mode: VideoTransitionMode = None,
    max_clip_duration: int = 5,
    min_clip_duration: float = 1.5,  # Thêm tham số thời lượng tối thiểu
    threads: int = 2,
) -> str:
    audio_clip = AudioFileClip(audio_file)
    audio_duration = audio_clip.duration
    logger.info(f"max duration of audio: {audio_duration} seconds")
    # Required duration of each clip
    req_dur = audio_duration / len(video_paths)
    req_dur = max_clip_duration
    logger.info(f"each clip will be maximum {req_dur} seconds long")
    output_dir = os.path.dirname(combined_video_path)

    aspect = VideoAspect(video_aspect)
    video_width, video_height = aspect.to_resolution()

    # Force garbage collection before starting
    gc.collect()

    # Log initial memory usage
    logger.info(f"Initial memory usage: {psutil.Process().memory_info().rss / 1024 / 1024:.2f} MB")

    clips = []
    video_duration = 0

    raw_clips = []
    for video_path in video_paths:
        try:
            # Check if file exists
            if not os.path.exists(video_path):
                logger.error(f"Video file does not exist: {video_path}")
                continue

            # Load video clip with moderate resolution to balance quality and memory usage
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            logger.info(f"Loading video {video_path}, file size: {file_size_mb:.2f} MB")

            # For 4K videos, use 1080p resolution to balance quality and memory usage
            # This is a good balance between quality and memory usage
            logger.info(f"Loading with 1080p resolution to balance quality and memory usage")

            # Load with 1080p resolution (1920x1080) which works well for most videos
            # This is much better quality than lower resolutions but still saves memory compared to 4K
            clip = VideoFileClip(video_path, target_resolution=(1080, 1920)).without_audio()
            clip_duration = clip.duration
            start_time = 0

            while start_time < clip_duration:
                end_time = min(start_time + max_clip_duration, clip_duration)
                split_clip = clip.subclipped(start_time, end_time)
                raw_clips.append(split_clip)
                # logger.info(f"splitting from {start_time:.2f} to {end_time:.2f}, clip duration {clip_duration:.2f}, split_clip duration {split_clip.duration:.2f}")
                start_time = end_time
                if video_concat_mode.value == VideoConcatMode.sequential.value:
                    break
        except Exception as e:
            logger.error(f"Error loading video {video_path}: {str(e)}")
            continue

    # Check if we have any clips to process
    if not raw_clips:
        logger.error("No valid video clips were loaded. Cannot create video.")
        raise ValueError("No valid video clips were loaded. Cannot create video.")

    # random video_paths order
    if video_concat_mode.value == VideoConcatMode.random.value:
        random.shuffle(raw_clips)

    # Lọc trước các clip có thời lượng quá ngắn
    filtered_raw_clips = []
    for clip in raw_clips:
        if clip.duration >= min_clip_duration:
            filtered_raw_clips.append(clip)
        else:
            logger.info(f"Filtering out clip with duration {clip.duration:.2f}s (less than minimum {min_clip_duration:.2f}s)")

    # Kiểm tra nếu không còn clip nào sau khi lọc
    if not filtered_raw_clips:
        logger.error("No clips with sufficient duration (>= {min_clip_duration:.2f}s) were found.")
        raise ValueError(f"No clips with sufficient duration (>= {min_clip_duration:.2f}s) were found.")

    # Sử dụng danh sách đã lọc
    raw_clips = filtered_raw_clips

    # Add downloaded clips over and over until the duration of the audio (max_duration) has been reached
    # Thêm biến đếm để tránh vòng lặp vô hạn
    max_iterations = 1000  # Giới hạn số lần lặp tối đa
    iteration_count = 0

    while video_duration < audio_duration and raw_clips and iteration_count < max_iterations:
        iteration_count += 1
        logger.info(f"Iteration {iteration_count}: Current video duration: {video_duration:.2f}s, Target: {audio_duration:.2f}s")

        for clip in raw_clips:
            # Kiểm tra nếu đã đủ thời lượng
            if video_duration >= audio_duration:
                break

            try:
                # Tạo bản sao của clip để tránh thay đổi clip gốc
                current_clip = clip.copy()

                # Check if clip is longer than the remaining audio
                if (audio_duration - video_duration) < current_clip.duration:
                    current_clip = current_clip.subclipped(0, (audio_duration - video_duration))
                # Only shorten clips if the calculated clip length (req_dur) is shorter than the actual clip to prevent still image
                elif req_dur < current_clip.duration:
                    current_clip = current_clip.subclipped(0, req_dur)
                current_clip = current_clip.with_fps(30)
            except Exception as e:
                logger.error(f"Error processing clip: {str(e)}")
                continue  # Skip this clip and continue with the next one

            # Not all videos are same size, so we need to resize them
            clip_w, clip_h = current_clip.size
            if clip_w != video_width or clip_h != video_height:
                clip_ratio = current_clip.w / current_clip.h
                video_ratio = video_width / video_height

                # Log video orientation and ratio
                is_portrait = clip_h > clip_w
                logger.info(f"Video orientation: {'Portrait' if is_portrait else 'Landscape'}, ratio: {clip_ratio:.2f}")

                if clip_ratio == video_ratio:
                    # Resize proportionally if ratios match
                    current_clip = current_clip.resized((video_width, video_height))
                else:
                        # For iPhone MOV files, we want to preserve the aspect ratio
                        # but ensure the video fills the frame as much as possible

                        # First, try direct resize to see if it works well
                        try:
                            # Simple resize to target dimensions
                            logger.info(f"Attempting direct resize from {clip_w}x{clip_h} to {video_width}x{video_height}")
                            current_clip = current_clip.resized((video_width, video_height))
                        except Exception as e:
                            logger.warning(f"Direct resize failed: {str(e)}, trying alternative method")

                            # If direct resize fails, use the standard approach with background
                            if clip_ratio > video_ratio:
                                # Resize proportionally based on the target width
                                scale_factor = video_width / clip_w
                            else:
                                # Resize proportionally based on the target height
                                scale_factor = video_height / clip_h

                            new_width = int(clip_w * scale_factor)
                            new_height = int(clip_h * scale_factor)
                            clip_resized = current_clip.resized(new_size=(new_width, new_height))

                            # Create a simple black background with lower memory usage
                            background = ColorClip(
                                size=(video_width, video_height), color=(0, 0, 0), duration=current_clip.duration
                            )

                            # Create composite clip with optimized memory usage
                            try:
                                current_clip = CompositeVideoClip(
                                    [
                                        background,
                                        clip_resized.with_position("center"),
                                    ],
                                    use_bgclip=True  # Use background as reference for size and duration
                                )
                            except Exception as e:
                                # Fallback if the optimized approach fails
                                logger.warning(f"Optimized composite failed, using standard approach: {str(e)}")
                                current_clip = CompositeVideoClip(
                                    [
                                        background,
                                        clip_resized.with_position("center"),
                                    ]
                                )

                logger.info(
                    f"resizing video to {video_width} x {video_height}, clip size: {clip_w} x {clip_h}"
                )

            shuffle_side = random.choice(["left", "right", "top", "bottom"])
            logger.info(f"Using transition mode: {video_transition_mode}")
            if video_transition_mode.value == VideoTransitionMode.none.value:
                # Không cần thay đổi
                pass
            elif video_transition_mode.value == VideoTransitionMode.fade_in.value:
                current_clip = video_effects.fadein_transition(current_clip, 1)
            elif video_transition_mode.value == VideoTransitionMode.fade_out.value:
                current_clip = video_effects.fadeout_transition(current_clip, 1)
            elif video_transition_mode.value == VideoTransitionMode.slide_in.value:
                current_clip = video_effects.slidein_transition(current_clip, 1, shuffle_side)
            elif video_transition_mode.value == VideoTransitionMode.slide_out.value:
                current_clip = video_effects.slideout_transition(current_clip, 1, shuffle_side)
            elif video_transition_mode.value == VideoTransitionMode.shuffle.value:
                transition_funcs = [
                    lambda c: video_effects.fadein_transition(c, 1),
                    lambda c: video_effects.fadeout_transition(c, 1),
                    lambda c: video_effects.slidein_transition(c, 1, shuffle_side),
                    lambda c: video_effects.slideout_transition(c, 1, shuffle_side),
                ]
                shuffle_transition = random.choice(transition_funcs)
                current_clip = shuffle_transition(current_clip)

            # Kiểm tra thời lượng tối đa một lần nữa (sau khi áp dụng hiệu ứng)
            if current_clip.duration > max_clip_duration:
                current_clip = current_clip.subclipped(0, max_clip_duration)

            try:
                # Add clip to list and update duration
                clips.append(current_clip)
                video_duration += current_clip.duration

                # Log success
                logger.info(f"Added clip with duration {current_clip.duration:.2f}s, total duration: {video_duration:.2f}s")
            except Exception as e:
                logger.error(f"Error adding clip to list: {str(e)}")
                # Skip this clip and continue with the next one

            # Log memory usage periodically
            if len(clips) % 5 == 0:
                logger.info(f"Memory usage after {len(clips)} clips: {psutil.Process().memory_info().rss / 1024 / 1024:.2f} MB")
                gc.collect()  # Force garbage collection periodically

    # Process clips in smaller batches to reduce memory usage
    logger.info(f"Processing {len(clips)} clips in batches")
    batch_size = 3  # Process 3 clips at a time to save memory
    processed_clips = []

    # Check if we have any clips to process
    if not clips:
        logger.error("No clips were added to the list. Cannot create video.")
        raise ValueError("No clips were added to the list. Cannot create video.")

    for i in range(0, len(clips), batch_size):
        batch = clips[i:i+batch_size]
        # Skip empty batches
        if not batch:
            logger.warning(f"Skipping empty batch at index {i}")
            continue

        # Wrap each clip in a CompositeVideoClip to ensure consistent format
        wrapped_batch = []
        for clip in batch:
            try:
                # Check if clip is valid
                if hasattr(clip, 'duration') and clip.duration > 0:
                    wrapped_clip = CompositeVideoClip([clip])
                    wrapped_batch.append(wrapped_clip)
                else:
                    logger.warning(f"Skipping invalid clip with no duration")
            except Exception as e:
                logger.error(f"Error wrapping clip in CompositeVideoClip: {str(e)}")
                # Skip this clip

        # Update batch with wrapped clips
        batch = wrapped_batch

        # Skip if batch is now empty
        if not batch:
            logger.warning(f"Batch at index {i} is empty after wrapping clips")
            continue

        # If this is not the first batch, concatenate with previous results
        if processed_clips:
            # Check if batch has enough clips before concatenating (need at least 1)
            if len(batch) > 0:
                try:
                    # If there's only one clip in the batch, no need to concatenate
                    if len(batch) == 1:
                        batch_clip = batch[0]
                        logger.info(f"Only one clip in batch, skipping concatenation")
                    else:
                        # Concatenate this batch
                        batch_clip = concatenate_videoclips(batch)

                    # Concatenate with previous results
                    # Check if processed_clips is a valid clip or a list
                    if isinstance(processed_clips, list) and not processed_clips:
                        # If processed_clips is an empty list, just use batch_clip
                        video_clip = batch_clip
                        logger.warning("processed_clips is empty, using only batch_clip")
                    else:
                        # If processed_clips is already a clip, concatenate with batch_clip
                        if hasattr(processed_clips, 'duration'):
                            video_clip = concatenate_videoclips([processed_clips, batch_clip])
                        else:
                            # If processed_clips is not a valid clip, just use batch_clip
                            logger.warning("processed_clips is not a valid clip, using only batch_clip")
                            video_clip = batch_clip
                except Exception as e:
                    logger.error(f"Error concatenating clips: {str(e)}")
                    # If there's an error, but we have at least one valid clip, use that
                    if hasattr(batch[0], 'duration'):
                        logger.warning("Using first clip in batch as fallback")
                        video_clip = batch[0]
                    else:
                        # If we can't even use the first clip, re-raise the exception
                        raise
                # Clean up to free memory
                del processed_clips
                del batch_clip
                gc.collect()
                # Store the result for the next iteration
                processed_clips = video_clip
            else:
                # If batch is empty, just keep the processed_clips
                logger.warning(f"Skipping empty batch at index {i}")
        else:
            # First batch, handle carefully
            if len(batch) > 0:
                try:
                    # If there's only one clip in the batch, no need to concatenate
                    if len(batch) == 1:
                        processed_clips = batch[0]
                        logger.info(f"Only one clip in first batch, skipping concatenation")
                    else:
                        # Concatenate this batch
                        processed_clips = concatenate_videoclips(batch)
                except Exception as e:
                    logger.error(f"Error concatenating first batch: {str(e)}")
                    # If there's an error, but we have at least one valid clip, use that
                    if hasattr(batch[0], 'duration'):
                        logger.warning("Using first clip in first batch as fallback")
                        processed_clips = batch[0]
                    else:
                        # If we can't even use the first clip, re-raise the exception
                        raise
            else:
                logger.warning(f"First batch is empty at index {i}")

        # Clean up batch to free memory
        del batch
        gc.collect()

        logger.info(f"Processed batch {i//batch_size + 1}/{(len(clips) + batch_size - 1)//batch_size}, memory usage: {psutil.Process().memory_info().rss / 1024 / 1024:.2f} MB")

    # Final result is in processed_clips
    # Check if we have any processed clips
    if not processed_clips:
        logger.error("No clips were processed successfully. Cannot create video.")
        raise ValueError("No clips were processed successfully. Cannot create video.")

    # If processed_clips is a list and not a VideoClip, handle the error
    if isinstance(processed_clips, list):
        if not processed_clips:
            logger.error("processed_clips is an empty list. Cannot create video.")
            raise ValueError("processed_clips is an empty list. Cannot create video.")
        # If it's a non-empty list, try to concatenate all clips in the list
        if len(processed_clips) > 0:
            logger.warning(f"processed_clips is a list with {len(processed_clips)} items. Attempting to concatenate.")
            processed_clips = concatenate_videoclips(processed_clips)

    video_clip = processed_clips
    video_clip = video_clip.with_fps(30)
    logger.info("writing video file...")
    # https://github.com/harry0703/MoneyPrinterTurbo/issues/111#issuecomment-2032354030
    try:
        # Log memory usage and video clip info
        logger.info(f"Memory usage before writing: {psutil.Process().memory_info().rss / 1024 / 1024:.2f} MB")
        logger.info(f"Video clip info - Duration: {video_clip.duration}, FPS: {video_clip.fps}, Size: {video_clip.size}")

        # Keep original resolution for better quality
        # No resolution reduction needed

        # Get threads from config or use the provided value
        ffmpeg_threads = config.app.get("ffmpeg_threads_per_process", threads)
        logger.info(f"Using {ffmpeg_threads} threads for FFMPEG")

        # Write the video file with optimized settings
        video_clip.write_videofile(
            filename=combined_video_path,
            threads=ffmpeg_threads,
            logger=None,
            temp_audiofile_path=output_dir,
            audio_codec="aac",
            codec="libx264",  # Explicitly set video codec
            fps=30,
            bitrate="2000k",  # Lower bitrate
            preset="ultrafast",  # Faster encoding
            ffmpeg_params=["-crf", "28"]  # Lower quality for smaller file size
        )

        # Log success and file size
        if os.path.exists(combined_video_path):
            logger.info(f"Video file written successfully. Size: {os.path.getsize(combined_video_path) / 1024 / 1024:.2f} MB")
        else:
            logger.error(f"Video file not found after writing: {combined_video_path}")

        logger.info(f"Memory usage after writing: {psutil.Process().memory_info().rss / 1024 / 1024:.2f} MB")
    except Exception as e:
        logger.error(f"Error writing video file: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Try to create an empty file to indicate an error occurred
        with open(f"{combined_video_path}.error.txt", "w") as f:
            f.write(f"Error: {str(e)}\n{traceback.format_exc()}")
        raise
    finally:
        try:
            video_clip.close()
            logger.info("Video clip closed successfully")
        except Exception as e:
            logger.error(f"Error closing video clip: {str(e)}")
        kill_ffmpeg_processes()
    logger.success("Video generation completed")
    return combined_video_path


def wrap_text(text, max_width, font="Arial", fontsize=60):
    # Create ImageFont
    font = ImageFont.truetype(font, fontsize)

    def get_text_size(inner_text):
        inner_text = inner_text.strip()
        left, top, right, bottom = font.getbbox(inner_text)
        return right - left, bottom - top

    width, height = get_text_size(text)
    if width <= max_width:
        return text, height

    # logger.warning(f"wrapping text, max_width: {max_width}, text_width: {width}, text: {text}")

    processed = True

    _wrapped_lines_ = []
    words = text.split(" ")
    _txt_ = ""
    for word in words:
        _before = _txt_
        _txt_ += f"{word} "
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            if _txt_.strip() == word.strip():
                processed = False
                break
            _wrapped_lines_.append(_before)
            _txt_ = f"{word} "
    _wrapped_lines_.append(_txt_)
    if processed:
        _wrapped_lines_ = [line.strip() for line in _wrapped_lines_]
        result = "\n".join(_wrapped_lines_).strip()
        height = len(_wrapped_lines_) * height
        # logger.warning(f"wrapped text: {result}")
        return result, height

    _wrapped_lines_ = []
    chars = list(text)
    _txt_ = ""
    for word in chars:
        _txt_ += word
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            _wrapped_lines_.append(_txt_)
            _txt_ = ""
    _wrapped_lines_.append(_txt_)
    result = "\n".join(_wrapped_lines_).strip()
    height = len(_wrapped_lines_) * height
    # logger.warning(f"wrapped text: {result}")
    return result, height


def generate_video(
    video_path: str,
    audio_path: str,
    subtitle_path: str,
    output_file: str,
    params: VideoParams,
):
    aspect = VideoAspect(params.video_aspect)
    video_width, video_height = aspect.to_resolution()

    logger.info(f"start, video size: {video_width} x {video_height}")
    logger.info(f"  ① video: {video_path}")
    logger.info(f"  ② audio: {audio_path}")
    logger.info(f"  ③ subtitle: {subtitle_path}")
    logger.info(f"  ④ output: {output_file}")

    # https://github.com/harry0703/MoneyPrinterTurbo/issues/217
    # PermissionError: [WinError 32] The process cannot access the file because it is being used by another process: 'final-1.mp4.tempTEMP_MPY_wvf_snd.mp3'
    # write into the same directory as the output file
    output_dir = os.path.dirname(output_file)

    font_path = ""
    if params.subtitle_enabled:
        if not params.font_name:
            params.font_name = "STHeitiMedium.ttc"
        font_path = os.path.join(utils.font_dir(), params.font_name)
        if os.name == "nt":
            font_path = font_path.replace("\\", "/")

        logger.info(f"using font: {font_path}")

    def create_text_clip(subtitle_item):
        params.font_size = int(params.font_size)
        params.stroke_width = int(params.stroke_width)
        phrase = subtitle_item[1]
        max_width = video_width * 0.9
        wrapped_txt, txt_height = wrap_text(
            phrase, max_width=max_width, font=font_path, fontsize=params.font_size
        )
        _clip = TextClip(
            text=wrapped_txt,
            font=font_path,
            font_size=params.font_size,
            color=params.text_fore_color,
            bg_color=params.text_background_color,
            stroke_color=params.stroke_color,
            stroke_width=params.stroke_width,
        )
        duration = subtitle_item[0][1] - subtitle_item[0][0]
        _clip = _clip.with_start(subtitle_item[0][0])
        _clip = _clip.with_end(subtitle_item[0][1])
        _clip = _clip.with_duration(duration)
        if params.subtitle_position == "bottom":
            _clip = _clip.with_position(("center", video_height * 0.95 - _clip.h))
        elif params.subtitle_position == "top":
            _clip = _clip.with_position(("center", video_height * 0.05))
        elif params.subtitle_position == "custom":
            # Ensure the subtitle is fully within the screen bounds
            margin = 10  # Additional margin, in pixels
            max_y = video_height - _clip.h - margin
            min_y = margin
            custom_y = (video_height - _clip.h) * (params.custom_position / 100)
            custom_y = max(
                min_y, min(custom_y, max_y)
            )  # Constrain the y value within the valid range
            _clip = _clip.with_position(("center", custom_y))
        else:  # center
            _clip = _clip.with_position(("center", "center"))
        return _clip

    # Load the video clip with moderate resolution to balance quality and memory usage
    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
    logger.info(f"Loading final video {video_path}, file size: {file_size_mb:.2f} MB")

    # For 4K videos, use 1080p resolution to balance quality and memory usage
    # This is a good balance between quality and memory usage
    logger.info(f"Loading final video with 1080p resolution to balance quality and memory usage")

    # Load with 1080p resolution (1920x1080) which works well for most videos
    # This is much better quality than lower resolutions but still saves memory compared to 4K
    video_clip = VideoFileClip(video_path, target_resolution=(1080, 1920))

    # Check video dimensions and ratio
    clip_w, clip_h = video_clip.size
    clip_ratio = clip_w / clip_h
    video_ratio = video_width / video_height

    is_portrait = clip_h > clip_w
    logger.info(f"Final video orientation: {'Portrait' if is_portrait else 'Landscape'}, ratio: {clip_ratio:.2f}")

    # Resize if needed to match target dimensions
    if clip_w != video_width or clip_h != video_height:
        logger.info(f"Resizing final video from {clip_w}x{clip_h} to {video_width}x{video_height}")
        video_clip = video_clip.resized((video_width, video_height))
    audio_clip = AudioFileClip(audio_path).with_effects(
        [afx.MultiplyVolume(params.voice_volume)]
    )

    def make_textclip(text):
        return TextClip(
            text=text,
            font=font_path,
            font_size=params.font_size,
        )

    if subtitle_path and os.path.exists(subtitle_path):
        sub = SubtitlesClip(
            subtitles=subtitle_path, encoding="utf-8", make_textclip=make_textclip
        )
        text_clips = []
        for item in sub.subtitles:
            clip = create_text_clip(subtitle_item=item)
            text_clips.append(clip)
        video_clip = CompositeVideoClip([video_clip, *text_clips])

    bgm_file = get_bgm_file(bgm_type=params.bgm_type, bgm_file=params.bgm_file)
    if bgm_file:
        try:
            bgm_clip = AudioFileClip(bgm_file).with_effects(
                [
                    afx.MultiplyVolume(params.bgm_volume),
                    afx.AudioFadeOut(3),
                    afx.AudioLoop(duration=video_clip.duration),
                ]
            )
            audio_clip = CompositeAudioClip([audio_clip, bgm_clip])
        except Exception as e:
            logger.error(f"failed to add bgm: {str(e)}")

    video_clip = video_clip.with_audio(audio_clip)
    try:
        # Log memory usage and video clip info
        logger.info(f"Memory usage before writing final video: {psutil.Process().memory_info().rss / 1024 / 1024:.2f} MB")
        logger.info(f"Final video clip info - Duration: {video_clip.duration}, FPS: {video_clip.fps}, Size: {video_clip.size}")

        # No resize needed for final video

        # Get threads from config or use the provided value
        ffmpeg_threads = config.app.get("ffmpeg_threads_per_process", params.n_threads or 2)
        logger.info(f"Using {ffmpeg_threads} threads for FFMPEG in final video")

        # Write the video file with optimized settings
        video_clip.write_videofile(
            output_file,
            audio_codec="aac",
            codec="libx264",  # Explicitly set video codec
            temp_audiofile_path=output_dir,
            threads=ffmpeg_threads,
            logger=None,
            fps=30,
            bitrate="2000k",  # Lower bitrate
            preset="ultrafast",  # Faster encoding
            ffmpeg_params=["-crf", "28"]  # Lower quality for smaller file size
        )

        # Log success and file size
        if os.path.exists(output_file):
            logger.info(f"Final video file written successfully. Size: {os.path.getsize(output_file) / 1024 / 1024:.2f} MB")
        else:
            logger.error(f"Final video file not found after writing: {output_file}")

        logger.info(f"Memory usage after writing final video: {psutil.Process().memory_info().rss / 1024 / 1024:.2f} MB")
    except Exception as e:
        logger.error(f"Error writing final video file: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Try to create an empty file to indicate an error occurred
        with open(f"{output_file}.error.txt", "w") as f:
            f.write(f"Error: {str(e)}\n{traceback.format_exc()}")
        raise
    finally:
        try:
            video_clip.close()
            del video_clip
            logger.info("Final video clip closed and deleted successfully")
        except Exception as e:
            logger.error(f"Error closing final video clip: {str(e)}")
        kill_ffmpeg_processes()
    logger.success("Final video generation completed")


def preprocess_video(materials: List[MaterialInfo], clip_duration=4):
    """Preprocess video materials to ensure they are in the correct format and duration."""
    try:
        for material in materials:
            if not material.url:
                continue

            ext = os.path.splitext(material.url)[1].lower()
            try:
                # First try to load as video if it's a video format
                if ext in ['.mov', '.mp4', '.avi', '.mkv', '.flv']:
                    try:
                        clip = VideoFileClip(material.url)
                        # Check video dimensions
                        width = clip.size[0]
                        height = clip.size[1]
                        if width < 480 or height < 480:
                            logger.warning(f"video is too small, width: {width}, height: {height}")
                            clip.close()
                            continue
                        # If it's a valid video, close it and continue
                        clip.close()
                        continue
                    except Exception as e:
                        logger.warning(f"Failed to load video clip {material.url}: {str(e)}")
                        continue
                else:
                    try:
                        clip = ImageClip(material.url)
                    except Exception as e:
                        logger.warning(f"Failed to load image clip {material.url}: {str(e)}")
                        continue

                width = clip.size[0]
                height = clip.size[1]
                if width < 480 or height < 480:
                    logger.warning(f"video is too small, width: {width}, height: {height}")
                    clip.close()
                    continue

                if ext in const.FILE_TYPE_IMAGES:
                    logger.info(f"processing image: {material.url}")
                    # Create an image clip and set its duration to 3 seconds
                    clip = (
                        ImageClip(material.url)
                        .with_duration(clip_duration)
                        .with_position("center")
                    )
                    # Apply zoom effect
                    zoom_clip = clip.resized(
                        lambda t: 1 + (clip_duration * 0.03) * (t / clip.duration)
                    )

                    final_clip = CompositeVideoClip([zoom_clip])

                    video_file = f"{material.url}.mp4"
                    # Get threads from config
                    ffmpeg_threads = config.app.get("ffmpeg_threads_per_process", 2)

                    # Write video file with thread limit
                    final_clip.write_videofile(video_file, fps=30, logger=None, threads=ffmpeg_threads)
                    final_clip.close()
                    del final_clip
                    material.url = video_file
                    logger.success(f"completed: {video_file}")
            except Exception as e:
                logger.warning(f"Failed to process material {material.url}: {str(e)}")
                continue
    finally:
        kill_ffmpeg_processes()
    return materials


if __name__ == "__main__":
    m = MaterialInfo()
    m.url = "/Users/harry/Downloads/IMG_2915.JPG"
    m.provider = "local"
    materials = preprocess_video([m], clip_duration=4)
    print(materials)

    # txt_en = "Here's your guide to travel hacks for budget-friendly adventures"
    # txt_zh = "测试长字段这是您的旅行技巧指南帮助您进行预算友好的冒险"
    # font = utils.resource_dir() + "/fonts/STHeitiMedium.ttc"
    # for txt in [txt_en, txt_zh]:
    #     t, h = wrap_text(text=txt, max_width=1000, font=font, fontsize=60)
    #     print(t)
    #
    # task_id = "aa563149-a7ea-49c2-b39f-8c32cc225baf"
    # task_dir = utils.task_dir(task_id)
    # video_file = f"{task_dir}/combined-1.mp4"
    # audio_file = f"{task_dir}/audio.mp3"
    # subtitle_file = f"{task_dir}/subtitle.srt"
    # output_file = f"{task_dir}/final.mp4"
    #
    # # video_paths = []
    # # for file in os.listdir(utils.storage_dir("test")):
    # #     if file.endswith(".mp4"):
    # #         video_paths.append(os.path.join(utils.storage_dir("test"), file))
    # #
    # # combine_videos(combined_video_path=video_file,
    # #                audio_file=audio_file,
    # #                video_paths=video_paths,
    # #                video_aspect=VideoAspect.portrait,
    # #                video_concat_mode=VideoConcatMode.random,
    # #                max_clip_duration=5,
    # #                threads=2)
    #
    # cfg = VideoParams()
    # cfg.video_aspect = VideoAspect.portrait
    # cfg.font_name = "STHeitiMedium.ttc"
    # cfg.font_size = 60
    # cfg.stroke_color = "#000000"
    # cfg.stroke_width = 1.5
    # cfg.text_fore_color = "#FFFFFF"
    # cfg.text_background_color = "transparent"
    # cfg.bgm_type = "random"
    # cfg.bgm_file = ""
    # cfg.bgm_volume = 1.0
    # cfg.subtitle_enabled = True
    # cfg.subtitle_position = "bottom"
    # cfg.n_threads = 2
    # cfg.paragraph_number = 1
    #
    # cfg.voice_volume = 1.0
    #
    # generate_video(video_path=video_file,
    #                audio_path=audio_file,
    #                subtitle_path=subtitle_file,
    #                output_file=output_file,
    #                params=cfg
    #                )
