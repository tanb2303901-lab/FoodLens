"""Stop only a process started here and its children, including Windows venv launchers."""
import psutil


def stop_child(process, timeout=15):
    """Popen.pid may be a launcher; terminating it alone can orphan the GPU worker."""
    try:
        parent=psutil.Process(process.pid)
    except psutil.NoSuchProcess:
        process.poll()
        return
    stop_tree(parent,timeout)
    process.poll()


def stop_tree(parent, timeout=15):
    """Caller must establish ownership of parent before passing it here."""
    try:children=parent.children(recursive=True)
    except psutil.NoSuchProcess:return
    targets=children[::-1]+[parent]
    for target in targets:
        try:target.terminate()
        except psutil.NoSuchProcess:pass
    _,alive=psutil.wait_procs(targets,timeout=timeout)
    for target in alive:
        try:target.kill()
        except psutil.NoSuchProcess:pass
    psutil.wait_procs(alive,timeout=5)
