#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dispatch_root="$(cd "$script_dir/.." && pwd)"
repo_root="$(cd "$dispatch_root/../../.." && pwd)"

env_file="${1:-$dispatch_root/.env.runner}"
label="com.specterlabs.dispatch-runner"
plist_path="${HOME}/Library/LaunchAgents/${label}.plist"
python_bin="${PYTHON_BIN:-$(command -v python3)}"
stdout_log="${HOME}/Library/Logs/${label}.out.log"
stderr_log="${HOME}/Library/Logs/${label}.err.log"

mkdir -p "${HOME}/Library/LaunchAgents" "${HOME}/Library/Logs"

cat >"${plist_path}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${python_bin}</string>
    <string>${script_dir}/runner.py</string>
    <string>--env-file</string>
    <string>${env_file}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${repo_root}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${stdout_log}</string>
  <key>StandardErrorPath</key>
  <string>${stderr_log}</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)" "${plist_path}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "${plist_path}"
launchctl kickstart -k "gui/$(id -u)/${label}"

echo "Installed ${label}"
echo "plist: ${plist_path}"
echo "stdout: ${stdout_log}"
echo "stderr: ${stderr_log}"
