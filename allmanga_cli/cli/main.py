"""Installed command entry point."""

import sys

from .. import app


def run():
    try:
        app.main()
    except KeyboardInterrupt:
        print(f"\n\n{app.YELLOW}Goodbye.{app.RESET}")
        return 130
    except Exception as exc:
        app.exit_alt_screen()
        if getattr(app, "DEBUG_MODE", False):
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
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
        app.flush_anilist_writes()
    return 0
