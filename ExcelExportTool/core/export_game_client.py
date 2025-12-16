# Author: huhongwei 306463233@qq.com
# Created: 2024-09-10
# MIT License 
# All rights reserved

import sys
from .export_process import batch_excel_to_json


def main():
    if len(sys.argv) < 3:
        print("用法: python export_game_client.py <Excel根目录> <客户端输出目录> [--no-diff] [--dry-run]")
        sys.exit(1)

    root_folder = sys.argv[1]
    output_client_folder = sys.argv[2]

    diff_only = True
    dry_run = False
    if "--no-diff" in sys.argv:
        diff_only = False
    if "--dry-run" in sys.argv:
        dry_run = True

    batch_excel_to_json(
        root_folder,
        output_client_folder=output_client_folder,
        diff_only=diff_only,
        dry_run=dry_run,
        auto_cleanup=True,
    )


if __name__ == '__main__':
    main()
