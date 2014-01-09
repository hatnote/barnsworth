# -*- coding: utf-8 -*-

_PDBed = False


def signal_handler(signal, frame):
    global _PDBed
    if _PDBed:
        return
    _PDBed = True

    gstacks = []
    try:
        import gc
        import traceback
        from greenlet import greenlet
        for ob in gc.get_objects():
            if isinstance(ob, greenlet):
                gstacks.append(''.join(traceback.format_stack(ob.gr_frame)))
    except Exception:
        print "couldn't collect (all) greenlet stacks"
    for i, gs in enumerate(gstacks):
        print '==== Stack', i + 1, '===='
        print gs
        print '------------'

    import pdb;pdb.set_trace()
    _PDBed = False


def install_signal_handler():
    import signal
    signal.signal(signal.SIGINT, signal_handler)
