# Writes sbaudio_version.h with the commit the program is built from, run on
# every build. "-dirty" means audio/ had uncommitted changes. The header is
# rewritten only when the stamp changes, so an unchanged tree rebuilds nothing.
#
#   cmake -DSRC=<audio dir> -DOUT=<header> -P version.cmake

execute_process(COMMAND git -C "${SRC}" rev-parse --short HEAD
                OUTPUT_VARIABLE commit OUTPUT_STRIP_TRAILING_WHITESPACE
                RESULT_VARIABLE rc ERROR_QUIET)
if(NOT rc EQUAL 0)
  set(commit "unknown")
else()
  execute_process(COMMAND git -C "${SRC}" status --porcelain -- .
                  OUTPUT_VARIABLE changes ERROR_QUIET)
  if(NOT changes STREQUAL "")
    set(commit "${commit}-dirty")
  endif()
endif()

set(text "// Written by version.cmake at build time; not committed.\n#define SBAUDIO_COMMIT \"${commit}\"\n")
set(old "")
if(EXISTS "${OUT}")
  file(READ "${OUT}" old)
endif()
if(NOT old STREQUAL text)
  file(WRITE "${OUT}" "${text}")
endif()
