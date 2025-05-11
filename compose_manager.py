#!/usr/bin/env python3
"""
Compose Manager CLI

A tool to generate and manage Docker Compose YAML files
with interactive, descriptive prompts via Rich & Questionary,
plus a scriptable build command.
Ensures consistent ordering and formatting of services and networks.
"""
import sys
import os
import subprocess
import click
import yaml as safe_yaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from rich.console import Console
from rich.table import Table
import questionary
from io import StringIO
from io import BytesIO
import re
import zipfile
import requests

__version__ = "0.2.0"
GITHUB_REPO = "Rabenherz112/compose-manager"

# Initialize the rich console for logging
env_console = Console()
# Configure ruamel.yaml to use two-space indents and preserve quotes
yaml = YAML()
yaml.indent(mapping=2, sequence=2, offset=2)
yaml.preserve_quotes = True

# Default resource limit presets
DEFAULT_PRESETS = {
    'Small': ('0.2', '64M'),
    'Medium': ('0.5', '128M'),
    'Big': ('1', '512M')
}

# Path to store user configuration
CONFIG_PATH = os.path.expanduser('~/.compose_manager_config.yml')

def load_config():
    """
    Load user configuration from CONFIG_PATH (infra file path and presets).
    Returns an empty dict if no config exists.
    """
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return safe_yaml.safe_load(f) or {}
    return {}

def save_config(cfg):
    """
    Persist the given config dict to CONFIG_PATH.
    """
    with open(CONFIG_PATH, 'w') as f:
        safe_yaml.safe_dump(cfg, f)

def init_infra(path):
    """
    Initialize a new infra compose file at 'path', creating directories as needed.
    Writes a basic YAML skeleton with empty services and networks.
    """
    root = CommentedMap({'services': CommentedMap(), 'networks': CommentedMap()})
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w') as f:
        yaml.dump(root, f)
    env_console.log(f"[green]Initialized infrastructure file:[/] {path}")

def order_service(cfg: CommentedMap) -> CommentedMap:
    """
    Reorder a service mapping with a consistent key sequence:
      container_name, image, restart, networks, ports,
      volumes, environment, depends_on, labels, deploy
    Any extra keys are appended afterwards.
    """
    desired = [
        'container_name', 'image', 'restart', 'networks', 'ports',
        'volumes', 'environment', 'depends_on', 'labels', 'deploy'
    ]
    ordered = CommentedMap()
    for key in desired:
        if key in cfg:
            ordered[key] = cfg.pop(key)
    for key, val in cfg.items():
        ordered[key] = val
    return ordered

def order_network(net_cfg: CommentedMap) -> CommentedMap:
    """
    Reorder a network mapping with keys: name, type, internal, external, enable_ipv6
    Extra properties follow.
    """
    key_order = ['name', 'type', 'internal', 'external', 'enable_ipv6']
    ordered = CommentedMap()
    for key in key_order:
        if key in net_cfg:
            ordered[key] = net_cfg.pop(key)
    for key, val in net_cfg.items():
        ordered[key] = val
    return ordered

def get_latest_release():
    """Return (tag_name, zipball_url) of the latest GitHub release."""
    api = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    r = requests.get(api, timeout=5)
    r.raise_for_status()
    j = r.json()
    return j["tag_name"], j["zipball_url"]

def download_and_extract(zip_url, target_dir):
    """Download the repo zipball and extract only relevant files."""
    r = requests.get(zip_url, timeout=10)
    r.raise_for_status()
    z = zipfile.ZipFile(BytesIO(r.content))

    wanted = {'compose_manager.py', 'setup_env.py'}

    prefix = z.namelist()[0]
    for member in z.infolist():
        relpath = os.path.relpath(member.filename, prefix)
        if member.is_dir() or relpath not in wanted:
            continue

        dest = os.path.join(target_dir, relpath)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with z.open(member) as src, open(dest, "wb") as out:
            out.write(src.read())
        print(f"  ↳ updated {relpath}")

def self_update():
    try:
        latest_tag, zip_url = get_latest_release()
    except Exception as e:
        print(f"[update] failed to fetch latest release: {e}", file=sys.stderr)
        return False

    if latest_tag <= __version__:
        return False

    print(f"Updating compose-manager: {__version__} → {latest_tag}…")
    repo_dir = os.path.abspath(os.path.dirname(__file__))
    download_and_extract(zip_url, repo_dir)

    setup = os.path.join(repo_dir, "setup_env.py")
    if os.path.isfile(setup):
        subprocess.run([sys.executable, setup, '--quiet'], check=True)

    print("Update complete; now re-launching with the new code.")
    os.execv(sys.executable, [sys.executable] + sys.argv)

@click.group(invoke_without_command=True)
@click.option(
    '--infra-file', '-F',
    default=lambda: load_config().get('infra_file', 'infra.yml'),
    help='Path to shared infra compose file defining networks'
)
@click.pass_context
def cli(ctx, infra_file):
    """
    CLI entrypoint: loads configuration and dispatches to subcommands
    or shows the interactive main menu if no command is given.
    """
    user_cfg = load_config()
    ctx.obj = {
        'infra_file': infra_file,
        'presets': user_cfg.get('presets', DEFAULT_PRESETS)
    }
    if ctx.invoked_subcommand is None:
        main_menu(ctx)

def main_menu(ctx):
    """
    Interactive menu to choose between wizard, script, settings, list, or exit.
    """
    while True:
        try:
            choice = questionary.select(
                'Main Menu - select action:',
                choices=[
                    '🆕 Wizard: interactive service editor',
                    '🛠️ Script: build via command-line args',
                    '⚙️ Settings: configure defaults',
                    '📄 List: show existing services',
                    '❌ Exit'
                ]
            ).ask()
        except KeyboardInterrupt:
            env_console.print("\n[red]Aborted by user[/]")
            sys.exit(0)

        if choice.startswith('🆕'):
            app = questionary.text('Application folder name:').ask()
            ctx.invoke(add_service, app_name=app)
        elif choice.startswith('🛠️'):
            app = questionary.text('Application folder name:').ask()
            ctx.invoke(build,
                        app_name=app,
                        service=[], restart='unless-stopped',
                        network=[], port=[], env=[],
                        preset='None', volume=[]
            )
        elif choice.startswith('⚙️'):
            configure_settings(ctx)
        elif choice.startswith('📄'):
            app = questionary.text('Application folder to list:').ask()
            ctx.invoke(list_services, app_name=app)
        else:
            sys.exit(0)

def configure_settings(ctx):
    """
    Wizard to configure the infra-file path and resource presets.
    Allows resetting, editing, or adding presets.
    """
    cfg = load_config()
    env_console.rule('[bold]Configure Defaults[/]')
    infra = questionary.text(
        'Infra compose file path:',
        default=cfg.get('infra_file', 'infra.yml')
    ).ask()

    presets = cfg.get('presets', DEFAULT_PRESETS)
    table = Table('Preset','CPUs','Memory')
    for name, (cpu, mem) in presets.items(): table.add_row(name, cpu, mem)
    env_console.print(table)

    if questionary.confirm('Reset all presets to default?').ask():
        presets = DEFAULT_PRESETS
    elif questionary.confirm('Edit existing presets?').ask():
        for name in list(presets):
            cpu = questionary.text(
                f"CPU count for '{name}':",
                default=presets[name][0]
            ).ask()
            mem = questionary.text(
                f"Memory limit for '{name}':",
                default=presets[name][1]
            ).ask()
            presets[name] = (cpu, mem)
        if questionary.confirm('Add a new preset?').ask():
            new = questionary.text('Preset name:').ask()
            cpu = questionary.text('CPUs:').ask()
            mem = questionary.text('Memory (e.g. 256M):').ask()
            presets[new] = (cpu, mem)

    # Save and report
    save_config({'infra_file': infra, 'presets': presets})
    env_console.print(f"[green]Settings saved to {CONFIG_PATH}[/]")
    ctx.obj['infra_file'] = infra
    ctx.obj['presets'] = presets

@cli.command('add')
@click.argument('app_name')
@click.pass_context
def add_service(ctx, app_name):
    """
    Interactive wizard to add or update services in <app_name>/compose.yml.
    Prompts for container_name, image, ports, volumes, environments, networks,
    resource limits, and optional comments.
    """
    infra = ctx.obj['infra_file']
    # Ensure infra compose exists
    if not os.path.exists(infra):
        if questionary.confirm(f"Infra file '{infra}' missing. Create it?").ask():
            init_infra(infra)
        else:
            env_console.print('[red]Infra compose file is required.[/]')
            sys.exit(1)

    # Load existing infra networks
    infra_cfg = yaml.load(open(infra)) or {}
    infra_nets = list(infra_cfg.get('networks', {}).keys())

    # Prepare application directory and compose file
    app_dir = os.path.join(os.getcwd(), app_name)
    os.makedirs(app_dir, exist_ok=True)
    target = os.path.join(app_dir, 'compose.yml')
    if not os.path.exists(target):
        yaml.dump(CommentedMap({'services': CommentedMap(), 'networks': CommentedMap()}), open(target, 'w'))

    general_comments = {}
    data = yaml.load(open(target)) or CommentedMap()
    services = data.setdefault('services', CommentedMap())
    nets_cfg = data.setdefault('networks', CommentedMap())

    # Loop through service definitions
    while True:
        svc = questionary.text('Service name (blank to finish):').ask()
        if not svc:
            break

        cfg = CommentedMap()
        # Container name
        cfg['container_name'] = questionary.text(
            'Container name (identifier):', default=svc
        ).ask()

        # Image
        img = questionary.text(
            'Docker image (repo:tag):'
        ).ask() or ''
        if ':' in img:
            cfg['image'] = img
        else:
            base = questionary.text('Base repository:', default=img).ask()
            tag = questionary.text('Tag (e.g. latest):', default='latest').ask()
            cfg['image'] = f"{base}:{tag}"

        # Restart policy
        policy = questionary.select(
            'Restart policy:',
            choices=[
                'unless-stopped – Restart unless stopped manually',
                'always – Always restart on exit',
                'on-failure – Restart on non-zero exit',
                'no – Do not restart'
            ]
        ).ask().split()[0]
        cfg['restart'] = policy

        # Dependencies
        if services:
            deps = questionary.checkbox(
                'Depends on (select other services):', choices=list(services.keys())
            ).ask() or []
            if deps:
                cfg['depends_on'] = CommentedSeq(deps)

        # Optional comments split by comma
        notes = questionary.text(
            'Optional notes/comments (comma-separated):'
        ).ask() or ''
        if notes:
            general_comments[svc] = notes

        # Ports
        ports = questionary.text(
            'Port mappings (host:container, comma-separated):'
        ).ask() or ''
        ps = [p.strip() for p in ports.split(',') if p.strip()]
        if ps:
            cfg['ports'] = CommentedSeq(ps)

        # Volumes
        vols = questionary.text(
            'Volume bindings (host:container, comma-separated):'
        ).ask() or ''
        vs = [v.strip() for v in vols.split(',') if v.strip()]
        if vs:
            cfg['volumes'] = CommentedSeq(vs)
            # Ensure host dirs exist
            for v in vs:
                host = v.split(':',1)[0]
                abs_h = host if os.path.isabs(host) else os.path.join(app_dir, host)
                os.makedirs(abs_h, exist_ok=True)

        # Environment variables
        envs = []
        if questionary.confirm('Include default env vars (PUID, PGID, TZ)?').ask():
            envs.extend(['PUID=1000', 'PGID=1000', 'TZ=Europe/Berlin'])
        extra_env = questionary.text(
            'Additional env vars (KEY=VALUE, comma-separated):'
        ).ask() or ''
        for e in [e.strip() for e in extra_env.split(',') if e.strip()]:
            envs.append(e)
        if envs:
            cfg['environment'] = CommentedSeq(envs)

        # Networks - existing
        attach = questionary.checkbox(
            'Attach to existing networks:',
            choices=[f"(E) {n}" if n in infra_nets else n for n in sorted(set(infra_nets + list(nets_cfg.keys())))]
        ).ask() or []
        attach = [a.replace('(E) ', '') for a in attach]
        for net in attach:
            props = {'name': net}
            if net in infra_nets:
                # external networks must not have a `type:` field
                props['external'] = True
            else:
                props['type'] = 'bridge'
            nets_cfg[net] = CommentedMap(props)
            cfg.setdefault('networks', CommentedSeq()).append(net)

        # Networks - new
        new_nets = questionary.text(
            'New networks to create (names, comma-separated):'
        ).ask() or ''
        for nn in [n.strip() for n in new_nets.split(',') if n.strip()]:
            kind = questionary.select(
                f"Type for network '{nn}':",
                choices=[
                    'external – external bridge network',
                    'internal – isolated internal network',
                    'internet – IPv6-enabled bridged network'
                ]
            ).ask().split()[0]
            props = {'name': nn}
            if kind == 'external':
                # external networks must not have a `type:` field
                props['external'] = True
            else:
                props['type'] = 'bridge'
                if kind == 'internal':
                    props['internal'] = True
                else:
                    # "internet" choice
                    props['enable_ipv6'] = True
            nets_cfg[nn] = CommentedMap(props)
            cfg.setdefault('networks', CommentedSeq()).append(nn)

        # Resource presets
        choices = [f"{n} – {c} CPUs, {m} memory" for n,(c,m) in ctx.obj['presets'].items()]
        choices += ['Custom – enter CPUs & memory', 'None – no limits']
        sel = questionary.select('Resource preset:', choices=choices).ask()
        if not sel.startswith('None'):
            if sel.startswith('Custom'):
                ccpus = questionary.text('Custom CPU count:').ask()
                cmem = questionary.text('Custom memory limit:').ask()
            else:
                pname = sel.split(' – ')[0]
                ccpus, cmem = ctx.obj['presets'][pname]
            cfg['deploy'] = CommentedMap([
                ('resources', CommentedMap([
                    ('limits', CommentedMap([
                        ('cpus', ccpus), ('memory', cmem)
                    ]))
                ]))
            ])

        # Watchtower auto-update label
        if questionary.confirm('Enable Watchtower auto-updates?').ask():
            cfg['labels'] = CommentedSeq(['com.centurylinklabs.watchtower.enable=true'])

        # Order and store service
        services[svc] = order_service(cfg)

    # Sort services and networks
    data['services'] = CommentedMap(sorted(services.items()))
    for net, props in list(nets_cfg.items()):
        nets_cfg[net] = order_network(props)
    data['networks'] = CommentedMap(sorted(nets_cfg.items()))

    # Dump YAML and inject comments for each service
    root = CommentedMap([('services', data['services']), ('networks', data['networks'])])
    buf = StringIO(); yaml.dump(root, buf)
    lines = buf.getvalue().splitlines()

    out = []
    current = None
    for line in lines:
        out.append(line)
        m = re.match(r"^  (\S[^:]+):$", line)
        if m:
            current = m.group(1)
            if current in general_comments:
                for note in general_comments[current].split(','):
                    out.append(f"    # {note.strip()}")
    with open(target, 'w') as f:
        f.write("\n".join(out) + "\n")

    # Validation step
    env_console.rule('[bold]Validation[/]')
    try:
        subprocess.run(['docker','compose','-f',target,'config'], check=True, capture_output=True, text=True)
        env_console.print('[green]Compose file is valid![/]')
    except subprocess.CalledProcessError as e:
        env_console.print(f"[red]Validation error:[/] {e.stderr}")
    except FileNotFoundError:
        env_console.print('[red]docker compose not found on PATH[/]')

    env_console.print(f"[bold green]Wrote compose to:[/] {target}")

@cli.command('list')
@click.argument('app_name')
@click.pass_context
def list_services(ctx, app_name):
    """
    Display a table of services defined in <app_name>/compose.yml,
    showing image, ports, networks, resource limits, etc.
    """
    target = os.path.join(os.getcwd(), app_name, 'compose.yml')
    if not os.path.exists(target):
        env_console.print(f"[red]No compose file found in '{app_name}'[/]")
        return
    data = yaml.load(open(target)) or {}

    table = Table(title=f"Services in '{app_name}'")
    cols = ['Name','Image','Ports','Networks','CPUs','Memory','Env','Volumes','Auto-Update']
    for c in cols: table.add_column(c)

    for name, cfg in data.get('services', {}).items():
        img = cfg.get('image','')
        ports = ','.join(cfg.get('ports',[])) or '—'
        nets = cfg.get('networks',[])
        net_display = []
        for n in nets:
            ext = data['networks'].get(n,{}).get('external')
            net_display.append(f"(E){n}" if ext else n)
        nets_str = ','.join(net_display) or '—'
        limits = cfg.get('deploy',{}).get('resources',{}).get('limits',{})
        cpus = limits.get('cpus','—'); mem = limits.get('memory','—')
        envs = ','.join(cfg.get('environment',[])) or '—'
        vols = ','.join(cfg.get('volumes',[])) or '—'
        auto = 'Yes' if 'com.centurylinklabs.watchtower.enable=true' in cfg.get('labels',[]) else 'No'
        table.add_row(name, img, ports, nets_str, cpus, mem, envs, vols, auto)

    env_console.print(table)

@cli.command('build')
@click.option('--app','app_name',required=True,
                help='Application folder to generate compose.yml')
@click.option('--service','-s',multiple=True,
                help='Specify services as container_name:image entries')
@click.option('--restart',default='unless-stopped',
                help='Restart policy for all generated services')
@click.option('--network','-n',multiple=True,
                help='Attach these networks to all services')
@click.option('--port','-p',multiple=True,
                help='Publish these ports on all services (host:container)')
@click.option('--env','-e',multiple=True,
                help='Set environment variables for all services (KEY=VALUE)')
@click.option('--preset','-r',default='None',
                help='Resource preset to apply to all services')
@click.option('--volume','-v',multiple=True,
                help='Bind mount these volumes on all services')
@click.pass_context
def build(ctx, app_name, service, restart, network, port, env, preset, volume):
    """
    Generate a basic compose.yml in script mode under <app_name>.
    Services, ports, networks, envs, volumes, and resource limits are
    taken from CLI options.
    """
    infra = ctx.obj['infra_file']
    if not os.path.exists(infra):
        init_infra(infra)

    app_dir = os.path.join(os.getcwd(), app_name)
    os.makedirs(app_dir, exist_ok=True)
    target = os.path.join(app_dir, 'compose.yml')

    data = CommentedMap([('services', CommentedMap()), ('networks', CommentedMap())])
    # Build each service from CLI args
    for s in service:
        name, img = s.split(':',1) if ':' in s else (s, '')
        cfg = CommentedMap([('container_name',name),('image',img)])
        cfg['restart'] = restart
        if network: cfg['networks'] = CommentedSeq(network)
        if port:    cfg['ports'] = CommentedSeq(port)
        if env:     cfg['environment'] = CommentedSeq(env)
        if volume:  cfg['volumes'] = CommentedSeq(volume)
        if preset!='None':
            if preset=='Custom':
                cpu = questionary.text('Custom CPUs:').ask()
                mem = questionary.text('Custom memory:').ask()
            else:
                cpu, mem = ctx.obj['presets'].get(preset,('',''))
            cfg['deploy'] = CommentedMap([
                ('resources',CommentedMap([
                    ('limits',CommentedMap([
                        ('cpus',cpu),('memory',mem)
                    ]))
                ]))
            ])
        data['services'][name] = order_service(cfg)

    # No networks by default in script mode
    data['networks'] = CommentedMap()
    # Dump to file
    with open(target,'w') as f:
        yaml.dump( CommentedMap([
            ('services',CommentedMap(sorted(data['services'].items()))),
            ('networks',data['networks'])
        ]), f)
    env_console.print(f"[green]Built compose file at:[/] {target}")

@cli.command()
def update():
    """Manually pull down and install the latest compose-manager from GitHub."""
    if not self_update():
        click.echo("Already up to date.")

if __name__=='__main__':
    try:
        if self_update():
            # os.execv above will replace this process, so we only get here on failure
            sys.exit(1)
    except Exception as e:
        print(f"[update] failed: {e}", file=sys.stderr)
    # Run the CLI
    cli()
