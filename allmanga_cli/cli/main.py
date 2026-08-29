"""Installed command entry point."""

import sys

from .. import app_core as app
from ..context import FLAGS as runtime_flags


def run():
    try:
        app.main()
    except KeyboardInterrupt:
        app.restore_terminal()
        return 130
    except Exception as exc:
        app.restore_terminal()
        if runtime_flags.debug_mode:
            try:
                log_path = app.write_exception_log("crash.log")
            except Exception as log_error:
                log_path = ""
                print(
                    f"\n{app.RED}Could not save crash traceback: "
                    f"{log_error}{app.RESET}"
                )
            print(f"\n{app.RED}An unexpected error occurred!{app.RESET}")
            if log_path:
                print(
                    f"{app.YELLOW}Traceback saved to "
                    f"{log_path}{app.RESET}"
                )
            return 1
        print(
            f"\n{app.RED}An unexpected error occurred: "
            f"{exc}{app.RESET}"
        )
        print(
            f"{app.YELLOW}Tip: run with --debug to save a private "
            f"crash traceback.{app.RESET}"
        )
        return 1
    finally:
        app.restore_terminal()
        app.flush_anilist_writes()
    return 0
