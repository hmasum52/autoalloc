import subprocess

namespace = 'kube-system'

p = subprocess.run(['kubectl', 'get', 'pods', f'-n={namespace}',
        r'-o=jsonpath={range .items[*]}{.metadata.uid} {.metadata.name}{"\n"}{end}'],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True, check=True)
print(p.stdout)
print(p.returncode)
print(p.stderr)