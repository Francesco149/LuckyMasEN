#!/usr/bin/env bash
# make-xp-cert.sh — throwaway self-signed cert for www.google.com that Windows XP
# SP3 Schannel/WinINet accept, for the gcal-emu HTTPS ClientLogin endpoint.
#
# Why these knobs (XP SP3 era):
#   * RSA-2048            — XP handles 2048 fine; avoid EC (XP Schannel can't).
#   * -sha1              — XP SP3 Schannel validates SHA-1 out of the box; SHA-256
#                          needs KB968730/938397 which may be absent. SHA-1 is safe.
#   * CN=localhost + SAN   — the deliverable byte-patches gcalcore.dll's host string
#                          www.google.com -> localhost (so XP keeps real internet, no
#                          hosts blackhole), so the client connects to "localhost" and
#                          the cert name must match it. CN=localhost covers XP WinINet
#                          even if it name-matches on the CN; the SAN also lists
#                          www.google.com et al. so the LEGACY hosts-redirect (unpatched
#                          binary) still validates on stacks that honor the SAN.
#   * 20y validity        — set-and-forget for a retro box (clock may even be wrong).
#   * minimal extensions  — a bare self-signed leaf. Installed into XP's Trusted Root
#                          it becomes its own trust anchor (CryptoAPI trusts a
#                          self-issued cert that's in ROOT regardless of CA:TRUE).
#
# NOT a secret: a fake-Google fixture for a LAN-isolated retro box. Committed so the
# served cert and the copy installed in XP's Root stay byte-identical (same thumbprint).
# Re-run only if you deliberately want a new identity (then re-install it on XP).
set -euo pipefail
d="$(cd "$(dirname "$0")" && pwd)/certs"
mkdir -p "$d"

openssl req -x509 -newkey rsa:2048 -sha1 -days 7300 -nodes \
  -keyout "$d/xp-google.key" -out "$d/xp-google.crt" \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,DNS:www.google.com,DNS:google.com,DNS:*.google.com"

# DER copy for XP-side import (certmgr / CertAddEncodedCertificateToStore / .reg blob).
openssl x509 -in "$d/xp-google.crt" -outform DER -out "$d/xp-google.der"

chmod 600 "$d/xp-google.key"
echo "--- generated $d/xp-google.{key,crt,der} ---"
openssl x509 -in "$d/xp-google.crt" -noout -subject -issuer -dates \
  -fingerprint -sha1 -ext subjectAltName
