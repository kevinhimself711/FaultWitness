#!/bin/sh
set -eu

step=bootstrap
cleanup_dir=
on_exit() {
    status=$?
    if [ -n "$cleanup_dir" ]; then
        rm -rf "$cleanup_dir"
    fi
    if [ "$status" -ne 0 ]; then
        printf 'FW_INSTALL_FAILED step=%s status=%s\n' "$step" "$status" >&2
    fi
}
trap on_exit 0

K3S_URL=@K3S_URL@
K3S_SHA256=@K3S_SHA256@
K3S_VERSION=@K3S_VERSION@
K3S_STAGE=@K3S_STAGE@
HELM_URL=@HELM_URL@
HELM_SHA256=@HELM_SHA256@
HELM_VERSION=@HELM_VERSION@
HELM_STAGE=@HELM_STAGE@

artifact_dir=/opt/faultwitness/artifacts
step=create-directories
mkdir -p "$artifact_dir" /etc/rancher/k3s

install_verified() {
    source=$1
    destination=$2
    expected=$3
    printf '%s  %s\n' "$expected" "$source" | sha256sum --check --status
    install -m 0644 "$source" "$destination"
}

step=stage-k3s
install_verified "$K3S_STAGE" "$artifact_dir/k3s-$K3S_VERSION" "$K3S_SHA256"
step=install-k3s-binary
install -m 0755 "$artifact_dir/k3s-$K3S_VERSION" /usr/local/bin/k3s

step=stage-helm
install_verified "$HELM_STAGE" "$artifact_dir/helm-$HELM_VERSION.tar.gz" "$HELM_SHA256"
step=install-helm-binary
helm_extract=$(mktemp -d)
cleanup_dir=$helm_extract
tar -xzf "$artifact_dir/helm-$HELM_VERSION.tar.gz" -C "$helm_extract"
install -m 0755 "$helm_extract/linux-amd64/helm" /usr/local/bin/helm

step=write-k3s-config
node_ip=$(ip -4 route get 1.1.1.1 | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}')
case "$node_ip" in
    10.*|192.168.*|172.1[6-9].*|172.2[0-9].*|172.3[0-1].*) ;;
    *) printf 'FW_INSTALL_FAILED step=private-node-ip status=1\n' >&2; exit 1 ;;
esac
cat >/etc/rancher/k3s/config.yaml <<FW_K3S_CONFIG
cluster-init: true
cluster-cidr: 10.42.0.0/16
service-cidr: 10.43.0.0/16
bind-address: $node_ip
# faultwitness.dev/listener-hardening=single-node-v1
flannel-backend: host-gw
tls-san:
  - 127.0.0.1
  - $node_ip
disable:
  - traefik
  - servicelb
secrets-encryption: true
write-kubeconfig-mode: "0600"
etcd-snapshot-schedule-cron: "0 */6 * * *"
etcd-snapshot-retention: 5
etcd-snapshot-dir: /var/lib/rancher/k3s/server/db/snapshots
node-label:
  - faultwitness.dev/owner=project
FW_K3S_CONFIG
chmod 0600 /etc/rancher/k3s/config.yaml

step=write-systemd-unit
cat >/etc/systemd/system/k3s.service <<'FW_K3S_UNIT'
[Unit]
Description=FaultWitness pinned K3s server
Documentation=https://k3s.io
Wants=network-online.target
After=network-online.target

[Service]
Type=notify
Environment=K3S_CONFIG_FILE=/etc/rancher/k3s/config.yaml
ExecStart=/usr/local/bin/k3s server
KillMode=process
Delegate=yes
LimitNOFILE=1048576
LimitNPROC=infinity
TasksMax=infinity
TimeoutStartSec=0
Restart=always
RestartSec=5s

[Install]
WantedBy=multi-user.target
FW_K3S_UNIT

step=start-k3s
systemctl daemon-reload
systemctl enable --now k3s.service

step=wait-k3s-ready
ready=false
attempt=0
while [ "$attempt" -lt 60 ]; do
    if /usr/local/bin/k3s kubectl get --raw=/readyz >/dev/null 2>&1; then
        ready=true
        break
    fi
    attempt=$((attempt + 1))
    sleep 2
done
[ "$ready" = true ]

step=verify-install
/usr/local/bin/k3s --version | grep -F "$K3S_VERSION" >/dev/null
/usr/local/bin/helm version --short | grep -F "$HELM_VERSION" >/dev/null
ss -H -lnt | awk '$4 ~ /:6443$/ {print $4}' | grep -Eq '^(127\.0\.0\.1|\[::1\]):6443$'
if ss -H -lnt | awk '$4 ~ /:6443$/ {print $4}' | grep -Ev '^(127\.0\.0\.1|\[::1\]):6443$' | grep -q .; then
    exit 1
fi
step=complete
