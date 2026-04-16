import asyncio
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def start_process(relative_script: str) -> subprocess.Popen:
    script_path = BASE_DIR / relative_script
    return subprocess.Popen([sys.executable, str(script_path)], cwd=BASE_DIR)


async def main() -> None:
    processes = [
        start_process('payment_bot/main.py'),
        start_process('msg_bot/main.py'),
        start_process('main.py'),
    ]

    try:
        while True:
            for process in processes:
                code = process.poll()
                if code is not None:
                    raise RuntimeError(f'Process exited early with code {code}: {process.args}')
            await asyncio.sleep(5)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        await asyncio.sleep(2)
        for process in processes:
            if process.poll() is None:
                process.kill()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass




