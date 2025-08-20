from pathlib import Path
from click.core import Group, Command
from hap.__main__ import cli


def _emit_command_help_md(group: Group) -> str:
    lines = ["## hap CLI commands", "", "Generated from Click introspection.", ""]
    for name, cmd in sorted(group.commands.items()):
        if isinstance(cmd, Group):
            lines.append(f"- {name}: {cmd.help or cmd.short_help or ''}".rstrip())
            for sub_name, sub in sorted(cmd.commands.items()):
                lines.append(f"  - {sub_name}: {sub.help or sub.short_help or ''}".rstrip())
        elif isinstance(cmd, Command):
            lines.append(f"- {name}: {cmd.help or cmd.short_help or ''}".rstrip())
    lines.append("")
    return "\n".join(lines)


def test_generate_commands_md(tmp_path):
    md = _emit_command_help_md(cli)
    out = Path("docs") / "COMMANDS.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    assert "build" in md and "sequence" in md and "config" in md
    assert out.exists() and out.stat().st_size > 0

