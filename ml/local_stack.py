"""Start the existing dedicated Docker stack, never create/reset/import data."""
import os
from pathlib import Path
import subprocess
import time


CONTAINERS=tuple('supabase_'+name+'_foodlens-local' for name in ('db','auth','rest','storage','kong'))


def ensure_local_stack():
    docker=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Docker/Docker/resources/bin/docker.exe'
    if not docker.is_file():raise RuntimeError('Installed Docker CLI is required for local API acceptance')
    def run(*args,timeout=20):
        return subprocess.run([str(docker),*args],capture_output=True,text=True,timeout=timeout,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if run('info','--format','{{.OSType}}').returncode:
        result=run('desktop','start','--timeout','120',timeout=130)
        if result.returncode:raise RuntimeError('Docker Desktop could not start for local acceptance')
    listed=run('container','ls','-a','--format','{{.Names}}')
    if listed.returncode or not set(CONTAINERS).issubset(set(listed.stdout.splitlines())):
        raise RuntimeError('Existing dedicated containers missing; no automatic recreate/reset is allowed')
    if run('start',*CONTAINERS,timeout=60).returncode:raise RuntimeError('Existing dedicated containers could not start')
    for _ in range(36):
        result=run('inspect','--format','{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}',*CONTAINERS)
        if result.returncode==0 and all(line in ('true healthy','true no-healthcheck') for line in result.stdout.splitlines()) and len(result.stdout.splitlines())==len(CONTAINERS):
            return
        time.sleep(5)
    raise RuntimeError('Existing local stack did not become healthy')
