# MeoArch 发布、频道、Installer 与 UI 总交接

这是本项目唯一的跨仓库实施交接与 Arch 执行 Runbook。它合并了原来的
`MEOARCH_IMPLEMENTATION_HANDOFF.md`、`ARCH_RELEASE_CHECKLIST.md` 和
`RELEASES.md`。复制到 Arch 工作站时只需要复制本文件。

更新时间：2026-08-27。

## 1. 不可改变的架构边界

```text
pacman repository configuration = 唯一频道真相
Installer = 初始频道和软件选择
OmniStore = 唯一官方 GUI 特权包管理入口
MeoSettings = 只读状态与跳转
meo-repo = 发布控制面
R2 = 包和 repo DB 分发
```

- Stable 只启用 `[meo]`。
- Beta 必须按 `[meo-beta]`、`[meo]` 排序；Beta 是稀疏 overlay，Stable 是完整 fallback。
- 频道由 `pacman-conf --repo-list` 的真实解析结果确定，不写客户端 preference。
- Beta → Stable 只能降级 `meo-release` catalog 中的官方 Meo 包，禁止 `pacman -Suu`。
- Settings 不运行 sudo、pacman 写事务或修改 pacman 配置。
- Build job 不接触 GPG 私钥、R2 写凭据或 Cloudflare purge token。

## 2. 当前真实实现

### meo-repo

已建立统一目录：`packages/`、`manifests/`、`scripts/`、`ci/`、`docs/`、`tests/`。
当前控制包和核心包配方包括：

```text
meoui-qml
meo-icons
meo-desktop
meo-settings
omnistore-bin
meo-keyring
meo-mirrorlist
meo-channel-stable
meo-channel-beta
meo-release
```

已有实现：

- Stable manifest 固定 tag、40 位 commit、expected package version、source SHA-256 和 compatibility generation。
- Stable train 构建所有核心包，任一失败则整个 train 不进入发布。
- Beta workflow 只接受一个明确 candidate，保留稀疏 overlay。
- 构建、签名/发布分 job；受保护 job 会重新校验 artifact hash 及包内 `.PKGINFO` 的 name/version/arch。
- 包和签名先上传并远程确认，再更新、签名和上传 DB/files DB。
- Stable 发布后使用 pacman `vercmp` 清理已被 Stable 追平的 Beta overlay。
- Stable 发布也会修改 Beta DB，因此发布使用全局不取消 concurrency lock。
- `SigLevel = Required TrustedOnly` 属于 channel package-owned 配置。
- host-independent release contract tests 当前为 14 项。

### Installer / ISO

真实 Installer 位于 `MeoArch_os-workspace/installer/`，没有第二套 GUI Installer。

已实现：

- 共享 Python `InstallConfig` / `RepositoryPlan` / `PackagePlan` / `InstallPlan`。
- Recommended、Minimal、Custom 和 Stable/Beta 选择。
- Custom 会把 `meo-desktop` 真正写入 config，并由共享 backend 强制 MeoUI/icons 依赖闭包。
- Python backend 生成的 `generated/install-plan.json` 会回传给 Qt Controller；Review 显示真实 repo 顺序和最终 Meo 包集合，不在 QML 复制依赖规则。
- 用户返回修改任何选择时，Controller 会废弃已准备 plan 和确认状态，必须重新 preflight，避免旧计划被安装。
- Review 在任何磁盘写入之前要求先准备计划，再单独确认擦除磁盘。
- QML 使用 MeoUI surfaces/theme roles；源测试禁止 raw Rectangle 和色值绕开设计系统。
- Installer 静态用户文字均进入 `qsTr()`，为完整翻译留下正确入口。
- sibling checkout 同时支持标准 `meo-ui` 和本机 `MeoUI` 名称，也可显式设置 `MEOUI_SOURCE_DIR`。
- CLI `meoarch-install` 与 GUI 复用包计划 backend，支持交互选择和 `--config` JSON/YAML。

### OmniStore

已有 `python/core/meo_channel.py`，频道从 pacman 读取，官方包集合从
`/usr/share/meo-release/package-catalog.json` 读取。

已实现：

- Stable → Beta：单独安装 channel package，事务结束后 `-Syyu` 正常升级。
- Beta → Stable：单独安装 Stable channel、刷新 DB、计算官方 Meo 包降级预览。
- Flutter Settings 中频道卡已接通 backend，无独立 preference。
- 频道卡使用 Material 3 segmented control、状态面板、repo priority、Beta 风险说明和降级待确认状态。
- 用户取消降级确认后仍保留“Review downgrades”入口，不会因频道已显示 Stable 而失去继续操作路径。
- backend 异常会保留上一次已知频道，不再把整个 UI 退回不明确的 Checking 状态。
- `core.sources` 改为按需加载；频道 helper 不再为了导入 privilege helper 而提前加载 AUR/GitHub 等网络插件。
- 测试依赖修正为公开包索引真实可安装的 `pytest==8.4.2` 和 `pytest-asyncio==1.2.0`。

### MeoSettings

Updates 页面保持只读：

- 从 `pacman-conf --repo-list` 解析 Stable/Beta 与仓库顺序。
- 只读显示缓存更新、来源和缓存时间，不运行 `-Sy`/`-Syu`。
- 显示 Meo repository priority。
- 紧凑宽度的操作按钮使用自动换行，避免三按钮固定 Row 溢出。
- “Manage updates & channel in OmniStore” 只负责打开 OmniStore。

## 3. 完整度审查：仍未做全的内容

| 优先级 | 仓库/区域 | 真实状态 | 需要完成 |
| --- | --- | --- | --- |
| P0 | meo-repo trust root | 缺少真实 `meo.gpg`、`meo-trusted`、`meo-revoked`；当前正确 fail closed | 离线生成 master/subkey，提交仅公钥 payload，并完成 disposable root populate 测试 |
| P0 | component release inputs | MeoUI、meo-kde、MeoSettings 缺计划 tag；OmniStore 现有旧 release 不含当前 exporter verifier | 创建评审 tag/release asset，记录 commit 和 SHA-256，填满 Stable manifest |
| P0 | OmniStore Stable rollback | UI 与安全预览存在，最终签名包下载/libalpm local-package transaction 未实现 | 按第 8 节实现；在此之前拒绝降级是正确行为 |
| P0 | Installer target payload | 安装计划会安装 pacman 包，但 `apply-target-customizations.sh` 仍从 Live runtime 复制 MeoUI/MeoKDE 运行时到目标 | 首个签名 Stable repo 可用后删除目标源码/runtime copy，目标只验证已安装包；Live ISO staging 可继续消费已验证源码 |
| P0 | Installer bootstrap | `installer/bootstrap/` 只有说明，没有已评审公钥 material | 放入与 `meo-keyring` 同源且 hash 固定的公开 bootstrap 文件 |
| P1 | CLI parity | CLI 当前只生成/打印 Meo 软件与频道 plan，不是完整磁盘、用户、网络、archinstall CLI | 在同一 Installer 中补全 full InstallConfig 输入和 runner；不要另建 CLI backend |
| P1 | Installer visual QA | 源码遵守 MeoUI token，但未在 Qt 运行时进行逐页 compact/desktop 截图比较 | Arch/Qt 上渲染 960×600、1440×900；检查文本换行、焦点、键盘导航和弹层 |
| P1 | Installer translation | 字符串已进入 `qsTr()`，但目前只有不完整的简中 `.ts`，其他语言 UI 名称不等于翻译完成 | 用 `lupdate` 重建 TS，完成至少 en/zh_CN/zh_TW/ja，再用 `lrelease` 验证 |
| P1 | Installer storage | 只支持经过验证的 erase-disk；manual partition 与 disk encryption 明确阻塞 | 基于真实 archinstall schema 实现并加 destructive VM tests，不能只解除 UI 禁用 |
| P1 | offline install | ISO 不携带完整本地 Meo repo | 当前明确 online-only；未来建立签名 local ISO repo + 安装后在线 channel |
| P1 | mirror UI | backend 首期只允许 automatic/packages.meoarch.org | 有第二个真实官方镜像后再增加 mirror 选择；不能把 mirror 和 channel 混合 |
| P1 | R2/CDN | workflow 和脚本存在，未对真实 R2 执行 | 配置 protected Environment 后跑首次 Stable/Beta 初始化及远程 smoke |
| P1 | end-to-end | 尚未完成 Live ISO → 安装 → reboot → pacman/Omni/Settings 一致性 | 按第 9 节跑 VM matrix 并保存证据 |
| P2 | OmniStore localization | 新频道卡的频道专用文案仍为英文，公共 Cancel/Refresh 已复用 l10n | 在 Flutter SDK 可用机器补 ARB 五语言并运行 `flutter gen-l10n` |
| P2 | OmniStore channel deep link | Settings 只能打开 OmniStore，不能直达频道锚点 | 为 OmniStore 定义稳定的内部 route/desktop action，再让 Settings 调用；不能以重复按钮假装 deep link |
| P2 | OmniStore Snap/custom repo | Snap plugin 仍是占位；Pacman custom repo 被安全禁用 | 是否支持由产品决定；若支持必须继续禁止编辑 `[meo]`/`[meo-beta]` |
| P2 | MeoSettings visual QA | MeoUI 结构已完成，当前机器无法渲染 Qt/KDE | 在 Plasma + MeoUI runtime 上验证 compact Flow、字体和仓库长名称 |

## 4. 创建不可变组件发布

不要强行创建旧 placeholder tag。对计划进入首个 train 的 commit 做评审 tag，并记录完整
40 位 commit ID。

2026-08-27 已知阻塞：

- `QwQdoge/MeoUI` 没有计划中的 `v1.0.2`。
- `QwQdoge/meo-kde` 没有计划中的 `v0.3.0`。
- `QwQdoge/MeoSettings` 没有计划中的 `v0.1.0`。
- OmniStore 只有旧 `v0.1.2`。其 release bundle SHA-256 是
  `e7220b46e35ba614e69a4b2727c5df4f116ed95f2886a5cca02661b751a6d7d3`，
  但该 tag 不含当前 `verify_release_exporter_contract.py`，不能进入新 train。

下载每个 immutable commit archive/release bundle，记录 SHA-256。源码包 URL 必须绑定
commit；OmniStore bundle 与 verifier 必须绑定同一 commit。填写 manifest 后运行：

```bash
python3 scripts/validate_manifest.py manifests/stable/<release>.json
python3 scripts/verify_manifest_sources.py manifests/stable/<release>.json
```

`expectedVersion` 必须精确等于 PKGBUILD 的 `pkgver-pkgrel`。

## 5. 建立离线信任根

在离线机器：

1. 创建 certification-only master key。
2. 创建有期限、可撤销、只用于包/repo DB 的 CI signing subkey。
3. 离线保存 fingerprint 和 revocation certificate。
4. 仅导出 CI signing subkey 给 protected GitHub Environment；master secret 永不联网。
5. 导出公开 pacman keyring：`meo.gpg`、`meo-trusted`、`meo-revoked`。

只把公开文件放入：

```text
meo-repo/packages/meo-keyring/files/
MeoArch_os-workspace/installer/bootstrap/
```

在 Arch disposable root 验证：

```bash
python3 scripts/validate_keyring_payload.py packages/meo-keyring/files
gpgdir="$(mktemp -d)"
pacman-key --gpgdir "$gpgdir" --init
# 把三个公开文件安装到临时 root 的 /usr/share/pacman/keyrings 后：
pacman-key --gpgdir "$gpgdir" --populate meo
```

不要把 `--recv-key` 或 `--lsign-key` 设计为正常安装流程。

## 6. Cloudflare R2 与 GitHub protected Environment

R2 需要 bucket、`packages.meoarch.org` custom domain、bucket-scoped Object Read/Write
token，以及只允许 exact cache purge 的 Cloudflare token。

GitHub `release` Environment 仅保存：

```text
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_ENDPOINT
R2_BUCKET
CLOUDFLARE_ZONE_ID
CLOUDFLARE_API_TOKEN
MEO_GPG_SIGNING_SUBKEY_B64
MEO_SIGNING_KEY_FINGERPRINT
```

必须启用 required reviewers。包对象使用 immutable long cache；DB/files DB 和签名使用
`no-cache,max-age=0,must-revalidate`，上传后只 purge 精确 URL。

R2 layout：

```text
meo/os/x86_64/<package>.pkg.tar.zst
meo/os/x86_64/<package>.pkg.tar.zst.sig
meo/os/x86_64/meo.db{,.sig}
meo/os/x86_64/meo.files{,.sig}
meo-beta/os/x86_64/<candidate>.pkg.tar.zst{,.sig}
meo-beta/os/x86_64/meo-beta.db{,.sig}
meo-beta/os/x86_64/meo-beta.files{,.sig}
```

首次 Beta 初始化临时设置 protected Environment variable：

```text
ALLOW_INITIAL_BETA_REPOSITORY=1
```

成功后立即移除或改为 `0`。后续 Beta 必须下载并验证现有签名 DB，再合并单一 candidate。

## 7. 发布操作

Stable dispatch：

```text
channel=stable
manifest=manifests/stable/<release>.json
beta_candidate=<empty>
```

Beta dispatch：

```text
channel=beta
manifest=<包含 candidate 身份的评审 manifest>
beta_candidate=<精确一个核心包名>
```

流水线顺序：

```text
unprivileged build/test/namcap/install smoke
→ hash-bound unsigned artifact
→ protected job 重新验证 hash 和 package metadata
→ sign package
→ upload package + .sig
→ remote existence verification
→ repo-add/repo-remove + sign DB
→ upload mutable DB
→ exact URL cache purge
→ remote signed pacman smoke
```

Stable 后由 `ci/cleanup-beta-overlay.sh` 验证两个 DB 签名、用 `vercmp` 比较并只删除
Stable 已追平的同名 Beta entry。

## 8. OmniStore 最终 Stable rollback（必须在 Arch 实现）

修改 `OmniStore/python/core/meo_channel.py`，继续使用现有频道状态和包管理器。若 bundled
Python 不能 import system `pyalpm`，增加一个窄 root helper，并把 `python-pyalpm` 加入包依赖。
helper 只接受版本化 JSON stdin，拒绝未知字段、包名、URL、shell 文本和任意 pacman 参数。

算法：

1. 获取 pacman DB lock，重新打开配置；确认 Meo subsequence 恰好是 `meo` 且无 `meo-beta`。
2. 只读取 `/usr/share/meo-release/package-catalog.json`，验证全部名称。
3. 对已安装官方包，从 `meo` sync DB 解析精确 candidate，使用 libalpm 版本比较。
4. 下载到新建 root-owned staging；按 `Required TrustedOnly` 完整验证包签名。
5. prepare 但不 commit 一次 local-package transaction；检查 to_add、to_remove、replace/conflict。
6. 若任何变化不在 catalog，或出现 Arch/第三方 remove/replace/upgrade/downgrade，立即 abort。
7. 返回完整 preview：name、installed、stable、SHA-256、canonical plan hash。
8. 二次确认后重新获取锁、重新解析，并要求 plan hash 未漂移。
9. 只 commit 该 local-package transaction；成功或失败都清理 staging。永远不运行 `-Suu`。

Arch tests：官方 Meo-only downgrade、`omnistore-bin` 例外、非 Meo dependency abort、无效签名、
plan drift、lock contention、partial download、disk full、transaction failure。

## 9. 验证矩阵

Host-independent：

```bash
# meo-repo
python3 -m unittest discover -s tests -v
python3 scripts/validate_manifest.py manifests/stable/<release>.json
python3 scripts/validate_keyring_payload.py

# Installer
python3 -m unittest discover -s installer/tests -v
bash scripts/acceptance/10-source-validation.sh
bash -n installer/backend/preflight-meo-repository.sh \
  installer/backend/configure-meo-repository.sh \
  installer/backend/run-archinstall.sh
```

Disposable Arch pacman roots必须覆盖：

- Stable first install/update。
- Beta overlay 优先和 Stable fallback。
- Stable 追平后的 overlay cleanup。
- channel package conflict 且无 replaces。
- unsigned/unknown/tampered package fail closed。
- unsigned/tampered DB fail closed。
- DB 引用缺失包。
- R2 immutable 包不能被不同内容覆盖。
- 并发 publication 串行且不 cancel。

VM matrix：

```text
Stable Recommended
Stable Minimal
Beta Recommended + fallback
Custom dependency closure
invalid signature before disk mutation
installed pacman-conf order
OmniStore/Settings channel agreement
Stable → Beta upgrade
Beta → Stable Meo-only downgrade
```

安装后 Stable：`pacman-conf --repo-list` 必须含 `meo` 且不含 `meo-beta`。
安装后 Beta：`meo-beta` 必须出现在 `meo` 之前。

## 10. 当前测试事实

截至本文件更新：

- meo-repo unittest：14/14 PASS。
- Installer unittest：47/47 PASS。
- Installer `scripts/acceptance/10-source-validation.sh`：PASS。
- OmniStore `python/tests/test_meo_channel.py`：4/4 PASS（临时隔离 pytest 环境）。
- `git diff --check`：各修改仓库应在提交前再次执行。

## 11. NOT VERIFIED

以下不能写成“已通过”：

- 真实 GPG keyring payload 与 `pacman-key --populate meo`。
- R2 写入、exact purge、远程对象一致性。
- Arch clean chroot package builds、namcap、repo-add/repo-remove。
- 包/DB 签名负面 pacman-root 测试。
- OmniStore 最终 signed Meo-only rollback executor。
- Flutter build/analyze/widget tests（当前工作站无 Flutter/Dart）。
- MeoSettings Qt/KDE build/test 和视觉渲染（当前工作站无 Qt/KF6）。
- ISO build、UEFI VM、Live → install → first boot。
- full CLI/TUI 与 GUI 的磁盘/用户/网络功能对等。

在这些项真实通过之前，发布脚本和 Installer 的 fail-closed 行为必须保留，不能降级为未签名、
跳过验证或继续安装。
