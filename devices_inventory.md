# 远程设备清单 (Devices Inventory)

所有远程服务器的快速连接信息，随时调取使用。

---

## 快速连接表

| 设备ID | 设备名 | IP地址 | SSH端口 | 用户名 | 密钥位置 | 用途 | 状态 |
|--------|--------|--------|---------|--------|----------|------|------|
| `vps-amadeus` | Amadeus VPS | 82.158.228.151 | 22 | root | `~/.ssh/amadeus_vps_key` | OpenClaw网关、Nginx代理 | ✅ 运行中 |
| `aliyun-1` | 阿里云1 | 139.196.101.174 | 55234 | root | `~/.openclaw/workspace/.ssh/aliyun_alcoen_erp` | 通用服务器 | ✅ 运行中 |
| `aliyun-2` | 阿里云2 | 47.101.209.149 | 2222 | root | `~/.ssh/aliyun2_rsa` | 备用服务器 | ✅ 运行中 |

---

## 一键连接命令

### VPS-Amadeus (OpenClaw网关)
`ash
ssh -i ~/.ssh/amadeus_vps_key root@82.158.228.151
`

### 阿里云1 (通用服务器)
```bash
ssh -p 55234 -i /root/.openclaw/workspace/.ssh/aliyun_alcoen_erp root@139.196.101.174
```

### 阿里云2 (备用服务器)
```bash
ssh -p 2222 -i /root/.ssh/aliyun2_rsa root@47.101.209.149
```

### PM安卓测试 (安卓测试服务器)
`ash
ssh -p 31467 -i ~/.ssh/id_ed25519 root@43.251.227.106
`

---

### `aliyun-1` - 阿里云1 (通用服务器)

| 属性 | 值 |
|------|-----|
| **公网IP** | 139.196.101.174 |
| **SSH端口** | 55234 |
| **登录用户** | root |
| **认证方式** | SSH密钥 |
| **密钥路径** | `/root/.openclaw/workspace/.ssh/aliyun_alcoen_erp` |
| **Web端口** | 80 (Nginx) |
| **系统** | Alibaba Cloud Linux 3 |
| **地区** | 国内（已备案） |

**主要服务：**
- Nginx反向代理
- 宝塔面板 (端口32148)

**详细配置记录：**
- 见 `memory/server_aliyun_alcoen_erp.md`

**代理配置：**
通过 VPS-Amadeus 的 Nginx 代理访问外网
- HTTP_PROXY: `http://82.158.228.151:3128`
- HTTPS_PROXY: `http://82.158.228.151:3128`

---

### `aliyun-2` - 阿里云2 (备用服务器)

| 属性 | 值 |
|------|-----|
| **公网IP** | 47.101.209.149 |
| **SSH端口** | 2222 |
| **登录用户** | root |
| **认证方式** | SSH密钥 |
| **密钥路径** | `/root/.ssh/aliyun2_rsa` |
| **Web端口** | 80/443 (Nginx), 888/32148 (宝塔) |
| **系统** | CentOS / Alibaba Cloud Linux |
| **地区** | 国内（已备案） |

**主要服务：**
- Nginx 反向代理
- 宝塔面板
- ERP系统 (Gunicorn 8080)

**连接信息：**
- SSH: `ssh -p 2222 -i ~/.ssh/aliyun2_rsa root@47.101.209.149`
- 宝塔: `https://47.101.209.149:32148`

---

## ➕ 待添加设备

| 设备ID | 设备名 | 计划用途 | 优先级 |
|--------|--------|----------|--------|
| `hk-vps` | 香港VPS | 免备案Web服务 | 高 |
| `local-dev` | 本地开发机 | 代码开发、测试 | 中 |

---

### 阿里云ERP (139.196.101.174)

| 项目 | 内容 |
|------|------|
| IP地址 | 139.196.101.174 |
| 用户名 | root |
| 密钥类型 | ED25519 |
| 密钥路径 | ~/.ssh/id_ed25519 |

SSH私钥：
`
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACAjY5Cd53CiBgHPs9wmNFaJVDClvh+5GfAF4Vy6mb2wIAAAAJjw657J8Oue
yQAAAAtzc2gtZWQyNTUxOQAAACAjY5Cd53CiBgHPs9wmNFaJVDClvh+5GfAF4Vy6mb2wIA
AAAEAxLpVLk+K+o+AdBLqc5eE1PLqplGnfoM6TE2sxclj5syNjkJ3ncKIGAc+z3CY0VolU
MKW+H7kZ8AXhXLqZvbAgAAAAFHJvb3RAaVpwaGp4aWgzcXcwMXNaAQ==
-----END OPENSSH PRIVATE KEY-----
`

公钥：
`
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICNjkJ3ncKIGAc+z3CY0VolUMKW+H7kZ8AXhXLqZvbAg root@iZphjxih3qw01sZ
`

连接命令：
`ash
ssh -i ~/.ssh/id_ed25519 root@139.196.101.174
`

---

### PM安卓测试 (43.251.227.106)

| 项目 | 内容 |
|------|------|
| **当前可用密钥** | `~/.ssh/amadeus_vps_key_new` |
| **密钥类型** | ED25519 |
| **公钥** | `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBMnK/Zz2mhIApLS+2ErWvyMIrNJm0yFAwW1BIRVA9Dd amadeus_vps_20260319` |
| **密钥指纹** | `SHA256:1/SBFbAjqcY3tWCeI5NMVipZvgN1HiGz2U1mSap899A` |

### 阿里云1 (aliyun-1) 密钥信息

| 项目 | 内容 |
|------|------|
| **密钥文件** | `aliyun_alcoen_erp` |
| **路径** | `/root/.openclaw/workspace/.ssh/aliyun_alcoen_erp` |
| **IP** | 139.196.101.174 |
| **端口** | 55234 |

### 阿里云2 (aliyun-2) 密钥信息

| 项目 | 内容 |
|------|------|
| **密钥文件** | `aliyun2_rsa` |
| **路径** | `/root/.ssh/aliyun2_rsa` |
| **IP** | 47.101.209.149 |
| **端口** | 2222 |
| **密钥类型** | RSA |

SSH私钥：
`
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEAjYnQB8i2oVaozRPFPzw0JZv2piTfRJqvBS9PEH0hs7ePtf9B
KXkbryA9tZKMVTFDfc7vLfGyx6+Co/bXEJNYzF13YQ7ds+e3F8HQQC8KHVbo4H+z
uVVdKcYGPq9TiX7TdwdHuak6tcQuiYd7uwePaF+1qdwhwClUN5Y+XPqfzvIyKjvT
I25+7Vlb86CVpgzdskpPVIPFek2WXNXRRccZO5/yL87X1JKrkpgsVFCcrLzWOl1S
rqbkMOuRn1L+hTXNOrF/9t3UDaO0iVuBYGEpBN+tmawEYaOPMWUvfREC59m/Z9MF
ODXXXYZnVQhy93sBKt06weMJ4AiY0tfDnK7fTwIDAQABAoIBACrZVGXu4T9RzXOc
byQYNU9HerHMytzpmV/P9TcwMsJGKZc3CgKku/lWIOh1z89AxUZynd1CZVXnr/y0
j2JgwUrJZwk2p26+ESN7lPDBbOX5+DFy57WNftFVNnHGwVsITrujtBakgXYiyNXw
8sfp34QBKa2dS4hx2qGjdgjPBQ9wtvAtLFBUyMJiBVMhNLWJrLLtzCtdakUElv6o
Hk/ODB5LJdgV0+dQYtXkHyNgpqlct+W4bTPi2TPDGEg/Arj2oGkQvP/3XD/GObrV
WHblr9x/X+YTM0TJBk0wglrzupnfle+57T+emTQVnWtDa/M5OW0TSvWlyTc48i+1
Td7hCLUCgYEAulU5mFdIkiU2PtRHrcdQBS1XB4Uo4hDcV/evMw80y5fIe3AKqM3u
uvnASlYVc4UQMXwqImEfGPddFfMp2qZItMXDnUYQmWARPbMu5ZyMwMQYBTsLSSQx
CToVukpbKL23EMXpj7L8TIt9mHUSYIVILEQ9+cglkUG1L/syoqWUXZUCgYEAwnUX
86uPg8ABNW34gPkFuzCQvWK0f0rtxqI4BJrpqCs3KA0hQkgcx69QcnXemEfyMyCU
lK1LjI96x6Cid2yC+i14l0H0ZKfm0R4ReEW78krXVGD84SYgxp6mifWYPUbjHlQv
x7sLdJR2z84whPoQWMIY/FvTJll2AN5pqIVQaFMCgYEAoTgcHTNoFwsbZEFHw5Qw
KEqSgm80cGUmQPaNICCIDZ/GVwcaMfP8Gsr9FVRmOw1mdWp5CkX+Ihvk7pj2HbjC
L6btGacFta7pO/lNGl3ZavA/2Ea9/QrTYqhfJFAxj46WVmznKO40XgZTJRYmUF0B
lUt2VChYWNYBbwJpTVD2jgECgYA7QnveIjZGLEkyAyVsCHeaqB4z2NSwxiDYG69+
l8cFHMZeSkIMdPVwVRjrCMihF6vTsOYWuQkA+Oit1WItisAPhbPuRIc59YD90W/5
eybfm7crW7M02e27GbYe7N1ML0IfiABXmcTP7j6W7XsTyzEYG26J2WHrme/ALAd+
98GdSQKBgAKIPaeftA6TC3FrhjAJlEyhzRNGaZgbn3SWT6iu5AnXGwH9YpLBuCiO
pQWfYC68YpaUwKEtqMy0vFrKKshajDIoP2+ZfSEnRdupJP8KQWRYgsryngKM/SVE
4pUEG2zFsx43GMKh3qj4DnjzZu/alot5v8PHC2ZSuAkibW6BYcC3
-----END RSA PRIVATE KEY-----
`

公钥：
`
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCNidAHyLahVqjNE8U/PDQlm/amJN9Emq8FL08QfSGzt4+1/0EpeRuvID21koxVMUN9zu8t8bLHr4Kj9tcQk1jMXXdhDt2z57cXwdBALwodVujgf7O5VV0pxgY+r1OJftN3B0e5qTq1xC6Jh3u7B49oX7Wp3CHAKVQ3lj5c+p/O8jIqO9Mjbn7tWVvzoJWmDN2ySk9Ug8V6TZZc1dFFxxk7n/IvztfUkquSmCxUUJysvNY6XVKupuQw65GfUv6FNc06sX/23dQNo7SJW4FgYSkE362ZrARho48xZS99EQLn2b9n0wU4NdddhmdVCHL3ewEq3TrB4wngCJjS18Ocrt9P
`

连接命令：
```bash
ssh -p 2222 -i ~/.ssh/aliyun2_rsa root@47.101.209.149
```

### 密钥丢失恢复方法

**如果本地密钥丢失，从 VPS 重新获取：**

```bash
# 方法1：从 VPS 下载（需要先有备用访问方式）
scp root@82.158.228.151:/root/.ssh/authorized_keys ~/.ssh/amadeus_vps_key.tmp

---

## 安全警告

| 方式 | 说明 |
|------|------|
| **宝塔面板** | https://82.158.228.151:32148 (aliyun-1) |
| **宝塔面板** | https://47.101.209.149:32148 (aliyun-2) |
| **VNC控制台** | 通过服务商后台 |
| **密码登录** | 如需开启：`PermitRootLogin yes` in `/etc/ssh/sshd_config` |

---

**最后更新：** 2026-03-24
**维护者：** Amadeus
