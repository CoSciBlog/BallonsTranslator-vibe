import os
import os.path as osp
import subprocess
from glob import glob

if __name__ == '__main__':
    program_dir = osp.dirname(osp.dirname(osp.abspath(__file__)))
    translate_dir = osp.dirname(osp.abspath(__file__)).replace('scripts', 'translate')
    ts_files = glob(osp.join(translate_dir, '*.ts'))

    ui_files = ' '.join(glob(osp.join(program_dir, 'ui/*.py')))
    lrelease_path = osp.join(program_dir, 'env', 'Lib', 'site-packages', 'qt6_applications', 'Qt', 'bin', 'lrelease.exe')
    
    for ts_file in ts_files:
        print(f'Updating language file: {osp.basename(ts_file)}')
        cmd = f'pylupdate6 {ui_files} -ts "{ts_file}"'
        subprocess.run(cmd, shell=True)
        print(f'Saved to {ts_file}')
        
        print(f'Compiling {osp.basename(ts_file)}')
        subprocess.run([lrelease_path, ts_file])