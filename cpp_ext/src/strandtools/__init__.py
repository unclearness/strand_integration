# CPP extension

# For Windows, need to add OpenCV dll directory before the extension loading
import platform
if platform.system() == 'Windows':
    import os
    import glob
    for p in os.environ["Path"].split(";"):
        dll_list = glob.glob(os.path.join(p, "opencv*.dll"))
        if len(dll_list) > 0:
            os.add_dll_directory(p)

from ._strandtools_impl import *
