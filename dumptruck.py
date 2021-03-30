#!/usr/bin/env python3
# dumps information about an aws account to a directory
# by: Cody Kochmann
# license: MIT
# last modified: 2021-03-30T05:50

import logging, os, string, subprocess, sys, itertools
from functools import lru_cache

''' This program dumps information about the
    configured aws environment by scanning awscli
    for list or describe operations and tries all
    of them to attempt to dump as much information
    as possible about the aws account into files
    under its settings.output_dir that can then
    be rapidly analyzed by tools like ugrep, fzf,
    jq and more.
'''

log = logging.getLogger(__name__)

if __name__ == '__main__':
    log.setLevel(logging.DEBUG)

class settings:
    formats = {
        'text': 'log',
        'table': 'txt',
        'json': 'json'
    }
    output_dir = './dumptruck'
    timeout = 300 # timeout of a command in seconds

@lru_cache(4096)
def run(*args, timeout=settings.timeout):
    return subprocess.run(
        args, 
        capture_output=True,
        timeout=timeout
    )

def working_command(*args):
    return run(*args).returncode == 0

def only_printables(s, whitelist=set(string.printable)):
    return ''.join(i for i in s if i in whitelist)

def shell(cmd):
    assert isinstance(cmd, str), cmd
    assert cmd.strip(), 'cmd cannot be empty string'
    log.info('running command: %s', cmd)
    # set up command
    pipe = run(*cmd.split(' ')).stdout.decode(errors='ignore').splitlines()
    # remove unprintables
    pipe = map(only_printables, pipe)
    # trim whitespace
    pipe = map(str.strip, pipe)
    # remove empty lines
    pipe = filter(bool, pipe)
    # yield output
    yield from pipe

@lru_cache(4096)
def service_help_doc(service_name):
    return [i for i in shell(f'aws {service_name} help')]
    
@lru_cache(4096)
def valid_service_command(service_name):
    try:
        service_help_doc(service_name)
    except:
        return False
    else:
        return True

def list_aws_services():
    pipe = shell('aws help')
    for i in pipe:
        log.debug('skipping: %s', i)
        if 'SSEERRVVIICCEESS' in i:
            break
    for i in pipe:
        if i.startswith('+o ') and len(i) >= 5:
            service_name = i[3:]
            if valid_service_command(service_name):
                yield service_name
            else:
                log.debug('invalid service name: %s', repr(service_name))
        else:
            break

def list_service_commands(service_name):
    assert isinstance(service_name, str), service_name
    assert service_name.strip()
    assert valid_service_command(service_name), service_name
    pipe = iter(service_help_doc(service_name))
    for i in pipe:
        log.debug('skipping: %s', i)
        if 'CCOOMMMMAANNDDSS' in i:
            break
    for i in pipe:
        if i.startswith('+o ') and len(i) >= 5:
            subcommand = i[3:]
            if (subcommand.startswith('list-') or subcommand.startswith('describe-')):
                if valid_service_command(f'{service_name} {subcommand}'):
                    yield service_name, subcommand
                else:
                    log.debug('invalid subcommand: %s %s', repr(service_name), repr(service_name))
            else:
                log.debug('skipping: %s %s', service_name, subcommand)
        else:
            break
    

def list_valid_dump_commands():
    for i in list_aws_services():
        print('---', i, file=sys.stderr)
        for svc, sub in list_service_commands(i):
            print('------', svc, sub, file=sys.stderr)
            if working_command('aws', svc, sub):
                print('---------', svc, sub, file=sys.stderr)
                yield svc, sub

@lru_cache(4096)
def mkdir(path):
    assert isinstance(path, str), path
    assert path.strip()
    if os.path.exists(path):
        assert os.path.isdir(path), path
    else:
        os.mkdir(path)

@lru_cache(4096)
def mkdir_p(path):
    assert isinstance(path, str), path
    assert path.strip()
    print('mkdir:', path, file=sys.stderr)
    return set(map(
        mkdir,
        itertools.accumulate(
            path.strip(os.path.sep).split(os.path.sep),
            os.path.join
        )
    ))
    
def capture_service_dump(service, subcommand, format, extension, output_dir):
    try:
        execution = run('aws', service, subcommand, '--output', format)
    except subprocess.TimeoutExpired:
        return
    if execution.returncode == 0:
        content = execution.stdout
        mkdir_p(os.path.join(output_dir, format, service))
        path = os.path.join(output_dir, format, service, f'{subcommand}.{extension}')
        with open(path, 'wb') as f:
            f.write(content)
        print('wrote:', path, file=sys.stderr)

def main(output_dir=settings.output_dir):
    for service, subcommand in list_valid_dump_commands():
        for format, extension in settings.formats.items():
            capture_service_dump(
                **locals()
            )
        
if __name__ == '__main__':
    main()
