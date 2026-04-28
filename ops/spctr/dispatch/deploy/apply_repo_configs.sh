#!/usr/bin/env bash
set -euo pipefail

repo_root="${SPECTER_REPO_ROOT:-/srv/specterlab/research-registry}"
deploy_root="${repo_root}/ops/spctr/dispatch/deploy"

if [[ ! -d "${deploy_root}" ]]; then
  echo "deploy assets are missing at ${deploy_root}" >&2
  exit 1
fi

sudo ln -sfn "${deploy_root}/Caddyfile" /etc/caddy/Caddyfile
sudo ln -sfn "${deploy_root}/specter-dispatch.service" /etc/systemd/system/specter-dispatch.service
sudo ln -sfn "${deploy_root}/specter-postgres-backup.service" /etc/systemd/system/specter-postgres-backup.service
sudo ln -sfn "${deploy_root}/specter-postgres-backup.timer" /etc/systemd/system/specter-postgres-backup.timer
sudo ln -sfn "${deploy_root}/specter-storagebox-sync.service" /etc/systemd/system/specter-storagebox-sync.service
sudo ln -sfn "${deploy_root}/specter-storagebox-sync.timer" /etc/systemd/system/specter-storagebox-sync.timer
sudo ln -sfn "${deploy_root}/specter-lake-reconcile.service" /etc/systemd/system/specter-lake-reconcile.service
sudo ln -sfn "${deploy_root}/specter-lake-reconcile.timer" /etc/systemd/system/specter-lake-reconcile.timer

spctr_deploy="${repo_root}/ops/spctr/deploy"
if [[ -d "${spctr_deploy}" ]]; then
  sudo mkdir -p /var/cache/spctr
  sudo chown specter:specter /var/cache/spctr
  sudo ln -sfn "${spctr_deploy}/spctr-report-cache.service" /etc/systemd/system/spctr-report-cache.service
  sudo ln -sfn "${spctr_deploy}/spctr-report-cache.timer" /etc/systemd/system/spctr-report-cache.timer
  sudo ln -sfn "${spctr_deploy}/99-specter-report" /etc/update-motd.d/99-specter-report
  sudo chmod +x /etc/update-motd.d/99-specter-report
fi

sudo install -d -o specter-deploy -g specter -m 2775 /srv/www/site/data
if [[ -e /srv/www/site/current || -L /srv/www/site/current ]]; then
  sudo ln -sfn /srv/www/site/data /srv/www/site/current/data
fi

sudo systemctl daemon-reload
sudo systemctl enable specter-dispatch
sudo systemctl enable specter-postgres-backup.timer
sudo systemctl enable specter-lake-reconcile.timer
sudo systemctl restart specter-lake-reconcile.timer
if [[ -d "${spctr_deploy}" ]]; then
  sudo systemctl enable spctr-report-cache.timer
fi
sudo systemctl reload caddy

if [[ "${SPECTER_REFRESH_LAKE_ON_DEPLOY:-0}" == "1" ]]; then
  sudo systemctl start specter-lake-reconcile.service
fi
