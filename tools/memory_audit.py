"""
CSC Memory Audit — Phase 16

Walks object graph and reports largest containers.
"""

import gc
import sys


def main(limit: int = 10) -> None:
    objs = gc.get_objects()
    sizes = sorted([(sys.getsizeof(o), type(o).__name__) for o in objs], reverse=True)
    for sz, tp in sizes[:limit]:
        print(f"{tp:<30} {sz/1024:8.1f} KB")


if __name__ == "__main__":
    main()
