"""Offline regression runner. No real model calls are authorized by this script."""
from pathlib import Path
import os,sys,unittest
root=Path(__file__).resolve().parents[1];os.chdir(root);sys.path.insert(0,str(root))
(root/'work').mkdir(exist_ok=True)
result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover(str(root),pattern='test_*.py'))
raise SystemExit(not result.wasSuccessful())
