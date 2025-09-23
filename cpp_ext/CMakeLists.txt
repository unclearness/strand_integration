cmake_minimum_required(VERSION  3.22.4)

project(strandtools LANGUAGES CXX)

if(NOT SKBUILD)
  message(WARNING "\
  This CMake file is meant to be executed using 'scikit-build'. Running
  it directly will almost certainly not produce the desired result. If
  you are a user trying to install this package, please use the command
  below, which will install all necessary build dependencies, compile
  the package in an isolated environment, and then install it.
  =====================================================================
   $ pip install .
  =====================================================================
  If you are a software developer, and this is your own package, then
  it is usually much more efficient to install the build dependencies
  in your environment once and use the following command that avoids
  a costly creation of a new virtual environment at every compilation:
  =====================================================================
   $ pip install nanobind scikit-build-core[pyproject]
   $ pip install --no-build-isolation -ve .
  =====================================================================
  You may optionally add -Ceditable.rebuild=true to auto-rebuild when
  the package is imported. Otherwise, you need to re-run the above
  after editing C++ files.")
endif()

# Try to import all Python components potentially needed by nanobind
find_package(Python 3.8
  REQUIRED COMPONENTS Interpreter Development.Module
  OPTIONAL_COMPONENTS Development.SABIModule)

# Import nanobind through CMake's find_package mechanism
find_package(nanobind CONFIG REQUIRED)

# We are now ready to compile the actual extension module
nanobind_add_module(

  # Name of the extension
  _strandtools_impl

  # Target the stable ABI for Python 3.12+, which reduces
  # the number of binary wheels that must be built. This
  # does nothing on older Python versions
  STABLE_ABI

  # Build libnanobind statically and merge it into the
  # extension (which itself remains a shared library)
  #
  # If your project builds multiple extensions, you can
  # replace this flag by NB_SHARED to conserve space by
  # reusing a shared libnanobind across libraries
  NB_STATIC

  # Source code goes here
  src/strandtools.cpp
)

# Install directive for scikit-build-core
install(TARGETS _strandtools_impl LIBRARY DESTINATION strandtools)

# Include directories
include_directories(src/include)

# OpenCV
find_package(OpenCV REQUIRED)
include_directories(${OpenCV_INCLUDE_DIRS})
# target_link_libraries(_strandtools_impl PRIVATE ${OpenCV_LIBS})
target_link_libraries(_strandtools_impl PRIVATE opencv_core opencv_imgproc)

# OpenMP
if(APPLE)
  find_package(OpenMP)

  if(NOT OpenMP_FOUND)
    message(STATUS "OpenMP not found, trying again with brew --prefix libomp")

    # Try again with extra path info; required for libomp 15+ from Homebrew
    execute_process(COMMAND brew --prefix libomp
      OUTPUT_VARIABLE HOMEBREW_LIBOMP_PREFIX
      OUTPUT_STRIP_TRAILING_WHITESPACE)
    set(OpenMP_C_FLAGS "-Xpreprocessor -fopenmp -I${HOMEBREW_LIBOMP_PREFIX}/include")
    set(OpenMP_CXX_FLAGS "-Xpreprocessor -fopenmp -I${HOMEBREW_LIBOMP_PREFIX}/include")
    set(OpenMP_C_LIB_NAMES omp)
    set(OpenMP_CXX_LIB_NAMES omp)
    set(OpenMP_omp_LIBRARY ${HOMEBREW_LIBOMP_PREFIX}/lib/libomp.dylib)
    find_package(OpenMP REQUIRED)
    
    message(STATUS "OpenMP_C_FLAGS: ${OpenMP_C_FLAGS}")
    message(STATUS "OpenMP_CXX_FLAGS: ${OpenMP_CXX_FLAGS}")
    message(STATUS "OpenMP_C_LIB_NAMES: ${OpenMP_C_LIB_NAMES}")
    message(STATUS "OpenMP_CXX_LIB_NAMES: ${OpenMP_CXX_LIB_NAMES}")
    message(STATUS "OpenMP_omp_LIBRARY: ${OpenMP_omp_LIBRARY}")
  endif()
else()
  find_package(OpenMP REQUIRED)
endif()

target_link_libraries(_strandtools_impl PRIVATE OpenMP::OpenMP_CXX)

# Export build-time OpenCV configuration for the Python import shim.
set(STRANDTOOLS_OPENCV_VERSION "${OpenCV_VERSION}")
if(NOT STRANDTOOLS_OPENCV_VERSION)
  set(STRANDTOOLS_OPENCV_VERSION "")
endif()

set(STRANDTOOLS_OPENCV_RUNTIME_DIRS "")

if(WIN32)
  get_target_property(_strandtools_linked_libraries _strandtools_impl LINK_LIBRARIES)
  set(_strandtools_opencv_targets "")

  foreach(_lib IN LISTS _strandtools_linked_libraries)
    if(_lib MATCHES "^\\$<")
      continue()
    endif()

    if(TARGET ${_lib} AND _lib MATCHES "^opencv_")
      list(APPEND _strandtools_opencv_targets ${_lib})
    elseif(EXISTS "${_lib}")
      get_filename_component(_lib_dir "${_lib}" DIRECTORY)
      list(APPEND STRANDTOOLS_OPENCV_RUNTIME_DIRS "${_lib_dir}")

      get_filename_component(_lib_parent "${_lib_dir}" DIRECTORY)
      if(_lib_parent)
        set(_bin_hint "${_lib_parent}")
        cmake_path(APPEND _bin_hint bin)
        list(APPEND STRANDTOOLS_OPENCV_RUNTIME_DIRS "${_bin_hint}")
      endif()
    endif()
  endforeach()

  list(REMOVE_DUPLICATES _strandtools_opencv_targets)

  foreach(_target IN LISTS _strandtools_opencv_targets)
    foreach(_prop IN ITEMS IMPORTED_LOCATION_RELEASE IMPORTED_LOCATION_RELWITHDEBINFO IMPORTED_LOCATION_MINSIZEREL IMPORTED_LOCATION_DEBUG IMPORTED_LOCATION)
      get_target_property(_opencv_location ${_target} ${_prop})
      if(_opencv_location)
        get_filename_component(_opencv_dir "${_opencv_location}" DIRECTORY)
        list(APPEND STRANDTOOLS_OPENCV_RUNTIME_DIRS "${_opencv_dir}")
      endif()
    endforeach()
  endforeach()

  if(OpenCV_RUNTIME_LIBRARY_DIRS)
    list(APPEND STRANDTOOLS_OPENCV_RUNTIME_DIRS ${OpenCV_RUNTIME_LIBRARY_DIRS})
  endif()

  if(OpenCV_BIN_DIR)
    list(APPEND STRANDTOOLS_OPENCV_RUNTIME_DIRS "${OpenCV_BIN_DIR}")
  endif()

  list(REMOVE_DUPLICATES STRANDTOOLS_OPENCV_RUNTIME_DIRS)
endif()

set(STRANDTOOLS_OPENCV_RUNTIME_DIRS_PY "")
foreach(_dir IN LISTS STRANDTOOLS_OPENCV_RUNTIME_DIRS)
  file(TO_CMAKE_PATH "${_dir}" _dir_norm)
  string(APPEND STRANDTOOLS_OPENCV_RUNTIME_DIRS_PY "    r\"${_dir_norm}\",\n")
endforeach()

set(_strandtools_opencv_config "${CMAKE_CURRENT_BINARY_DIR}/generated/_opencv_config.py")
configure_file(
  ${CMAKE_CURRENT_SOURCE_DIR}/src/strandtools/_opencv_config.in.py
  ${_strandtools_opencv_config}
  @ONLY
)

install(FILES ${_strandtools_opencv_config} DESTINATION strandtools)
