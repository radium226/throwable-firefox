#!/usr/bin/env python

from throwablefirefox.shell import execute

def subdl(video_file_path):
    command = [
        "subdl",
        "--existing=overwrite",
        f"./{video_file_path.name}"
    ]
    execute(command, in_folder=video_file_path.parent)
    return video_file_path.parent / f"{video_file_path.stem}.srt"
