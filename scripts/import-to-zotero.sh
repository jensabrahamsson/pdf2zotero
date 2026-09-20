#!/usr/bin/env bash
# import-to-zotero.sh — Helautomatiserad import av PDF till Zotero.
#
# Användning:
#   ./scripts/import-to-zotero.sh fil.pdf [fil2.pdf ...]
#   ./scripts/import-to-zotero.sh --install     # Installerar Finder-snabbåtgärden
#
# Gör hela kedjan:
# 1. Kontrollerar och startar Docker Desktop om det behövs (med live-status).
# 2. Kontrollerar och startar GROBID-containern på port 8070 (med live-status).
# 3. Säkerställer att Zotero är startat.
# 4. Extraherar metadata och hämtar officiell DOI/BibTeX via pdf2zotero.py.
# 5. Öppnar den genererade .bib-filen i Zotero (samma File -> Import som i dokumentationen).
# 6. Visar tydlig status och framsteg både i terminalen och via macOS-notiser.
#    Kontrollera att PDF:en sitter som bifogad fil under posten.
#
# Copyright (c) 2026 Jens Abrahamsson. Released under the MIT License.

set -euo pipefail

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

log_info() {
  echo -e "\033[1;34m[INFO]\033[0m $*"
}

log_step() {
  echo -e "\033[1;32m==>\033[0m \033[1m$*\033[0m"
}

log_warn() {
  echo -e "\033[1;33m[VARNING]\033[0m $*" >&2
}

log_err() {
  echo -e "\033[1;31m[FEL]\033[0m $*" >&2
}

notify() {
  local msg="$1"
  local subtitle="${2:-}"
  if [ -n "$subtitle" ]; then
    osascript -e "display notification \"${msg}\" with title \"pdf2zotero\" subtitle \"${subtitle}\"" 2>/dev/null || true
  else
    osascript -e "display notification \"${msg}\" with title \"pdf2zotero\"" 2>/dev/null || true
  fi
}

alert_error() {
  local msg="$1"
  log_err "$msg"
  osascript -e "display alert \"pdf2zotero fel\" message \"${msg}\" as critical" 2>/dev/null || true
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PDF2ZOTERO_PY="${SCRIPT_DIR}/pdf2zotero.py"

install_finder_service() {
  local service_dir="${HOME}/Library/Services/Importera till Zotero.workflow"
  local script_path="${SCRIPT_DIR}/scripts/import-to-zotero.sh"

  log_step "Installerar Snabbåtgärd i Finder..."
  mkdir -p "${service_dir}/Contents/Resources"

  cat > "${service_dir}/Contents/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key>
	<string>sv_SE</string>
	<key>CFBundleIdentifier</key>
	<string>se.makeitso.pdf2zotero.importService</string>
	<key>CFBundleName</key>
	<string>Importera till Zotero</string>
	<key>CFBundleShortVersionString</key>
	<string>1.0</string>
	<key>NSServices</key>
	<array>
		<dict>
			<key>NSMenuItem</key>
			<dict>
				<key>default</key>
				<string>Importera till Zotero</string>
			</dict>
			<key>NSMessage</key>
			<string>runWorkflowAsService</string>
			<key>NSRequiredContext</key>
			<dict>
				<key>NSApplicationIdentifier</key>
				<string>com.apple.finder</string>
			</dict>
			<key>NSSendFileTypes</key>
			<array>
				<string>com.adobe.pdf</string>
			</array>
		</dict>
	</array>
</dict>
</plist>
EOF

  cat > "${service_dir}/Contents/document.wflow" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>AMApplicationBuild</key>
	<string>523</string>
	<key>AMApplicationVersion</key>
	<string>2.10</string>
	<key>AMDocumentVersion</key>
	<string>2</string>
	<key>actions</key>
	<array>
		<dict>
			<key>action</key>
			<dict>
				<key>AMAccepts</key>
				<dict>
					<key>Container</key>
					<string>List</string>
					<key>Optional</key>
					<false/>
					<key>Types</key>
					<array>
						<string>com.apple.cocoa.path</string>
					</array>
				</dict>
				<key>AMActionVersion</key>
				<string>2.0.3</string>
				<key>AMApplication</key>
				<array>
					<string>Automator</string>
				</array>
				<key>AMParameterProperties</key>
				<dict>
					<key>COMMAND_STRING</key>
					<dict/>
					<key>CheckedForUserDefaultShell</key>
					<dict/>
					<key>inputMethod</key>
					<dict/>
					<key>shell</key>
					<dict/>
					<key>source</key>
					<dict/>
				</dict>
				<key>AMProvides</key>
				<dict>
					<key>Container</key>
					<string>List</string>
					<key>Types</key>
					<array>
						<string>com.apple.cocoa.path</string>
					</array>
				</dict>
				<key>ActionBundlePath</key>
				<string>/System/Library/Automator/Run Shell Script.action</string>
				<key>ActionName</key>
				<string>Run Shell Script</string>
				<key>ActionParameters</key>
				<dict>
					<key>COMMAND_STRING</key>
					<string>"${script_path}" "\$@"</string>
					<key>CheckedForUserDefaultShell</key>
					<true/>
					<key>inputMethod</key>
					<integer>1</integer>
					<key>shell</key>
					<string>/bin/zsh</string>
					<key>source</key>
					<string></string>
				</dict>
				<key>BundleIdentifier</key>
				<string>com.apple.RunShellScript</string>
				<key>CFBundleVersion</key>
				<string>2.0.3</string>
				<key>CanShowSelectedItemsWhenRun</key>
				<false/>
				<key>CanShowWhenRun</key>
				<true/>
				<key>Category</key>
				<array>
					<string>AMCategoryUtilities</string>
				</array>
				<key>Class Name</key>
				<string>RunShellScriptAction</string>
				<key>InputUUID</key>
				<string>C4C44192-33E8-44B4-A112-34B123F72B6B</string>
				<key>Keywords</key>
				<array>
					<string>Shell</string>
					<string>Script</string>
					<string>Command</string>
					<string>Run</string>
					<string>Unix</string>
				</array>
				<key>OutputUUID</key>
				<string>F17AB958-FBF0-4981-BC35-F65D339BEEF3</string>
				<key>UUID</key>
				<string>1D1ED2AB-83CF-4826-AC1B-2C117AC5F9B3</string>
				<key>UnlocalizedApplications</key>
				<array>
					<string>Automator</string>
				</array>
			</dict>
		</dict>
	</array>
	<key>connectors</key>
	<dict/>
	<key>workflowMetaData</key>
	<dict>
		<key>serviceApplicationBundleID</key>
		<string>com.apple.finder</string>
		<key>serviceApplicationPath</key>
		<string>/System/Library/CoreServices/Finder.app</string>
		<key>serviceInputTypeIdentifier</key>
		<string>com.apple.Automator.fileSystemObject.PDF</string>
		<key>serviceOutputTypeIdentifier</key>
		<string>com.apple.Automator.nothing</string>
		<key>serviceProcessesInput</key>
		<integer>0</integer>
		<key>workflowTypeIdentifier</key>
		<string>com.apple.Automator.servicesMenu</string>
	</dict>
</dict>
</plist>
EOF

  cp "${service_dir}/Contents/document.wflow" "${service_dir}/Contents/Resources/document.wflow"
  /System/Library/CoreServices/pbs -update 2>/dev/null || true

  log_step "Klart! 'Importera till Zotero' är installerad."
  echo "Du kan nu högerklicka på valfri PDF i Finder -> Snabbåtgärder -> Importera till Zotero."
}

if [ "${1:-}" = "--install" ]; then
  install_finder_service
  exit 0
fi

if [ ! -f "$PDF2ZOTERO_PY" ]; then
  alert_error "Kunde inte hitta pdf2zotero.py i ${SCRIPT_DIR}"
  exit 1
fi

if [ "$#" -eq 0 ]; then
  log_err "Ingen PDF-fil angiven."
  echo "Användning: $0 <fil1.pdf> [fil2.pdf ...] eller $0 --install"
  notify "Ingen PDF-fil angiven." "Avbruten"
  exit 1
fi

# -------------------------------------------------------------
# Steg 1: Kontrollera och starta Docker om det behövs
# -------------------------------------------------------------
log_step "Steg 1/4: Kontrollerar Docker..."
if ! docker info >/dev/null 2>&1; then
  log_info "Docker är inte igång. Startar Docker Desktop..."
  notify "Startar Docker Desktop..." "Vänligen vänta"

  if [ -d "/Applications/Docker.app" ]; then
    open -a Docker
  elif command -v colima >/dev/null 2>&1; then
    colima start
  else
    open -a Docker || true
  fi

  waited=0
  max_wait=90
  while ! docker info >/dev/null 2>&1; do
    sleep 2
    waited=$((waited + 2))
    log_info "Väntar på Docker daemon... (${waited}s / ${max_wait}s)"
    if [ "$waited" -ge "$max_wait" ]; then
      alert_error "Docker startade inte inom ${max_wait} sekunder. Starta Docker Desktop manuellt och försök igen."
      exit 1
    fi
  done
  log_info "Docker Desktop är nu igång!"
else
  log_info "Docker körs redan."
fi

# -------------------------------------------------------------
# Steg 2: Kontrollera och starta GROBID
# -------------------------------------------------------------
log_step "Steg 2/4: Kontrollerar GROBID-tjänsten..."
if ! curl -sf "http://127.0.0.1:8070/api/isalive" 2>/dev/null | grep -qi true; then
  log_info "GROBID svarar inte på port 8070. Startar containern..."
  notify "Startar GROBID..." "Laddar modeller på :8070"

  if docker ps -a --format '{{.Names}}' | grep -qx grobid; then
    docker start grobid >/dev/null
  else
    log_info "Containern 'grobid' saknas. Kör setup-grobid.sh..."
    if ! "${SCRIPT_DIR}/scripts/setup-grobid.sh" up; then
      alert_error "setup-grobid.sh up misslyckades."
      exit 1
    fi
  fi

  waited=0
  max_wait=180
  while ! curl -sf "http://127.0.0.1:8070/api/isalive" 2>/dev/null | grep -qi true; do
    sleep 5
    waited=$((waited + 5))
    log_info "Väntar på att GROBID ska svara... (${waited}s / ${max_wait}s)"
    if [ "$waited" -ge "$max_wait" ]; then
      alert_error "GROBID startade inte inom ${max_wait} sekunder på http://127.0.0.1:8070."
      exit 1
    fi
  done
  log_info "GROBID är igång och svarar!"
else
  log_info "GROBID körs redan."
fi

# -------------------------------------------------------------
# Steg 3: Kontrollera Zotero
# -------------------------------------------------------------
log_step "Steg 3/4: Öppnar Zotero..."
open -a Zotero

# -------------------------------------------------------------
# Steg 4: Konvertera PDF och importera till Zotero
# -------------------------------------------------------------
log_step "Steg 4/4: Bearbetar och importerar filer..."
failed=0
for pdf_file in "$@"; do
  if [ ! -f "$pdf_file" ]; then
    log_warn "Filen finns inte: $pdf_file"
    failed=$((failed + 1))
    continue
  fi

  base_name="$(basename "$pdf_file")"
  log_info "Bearbetar: ${base_name}"
  notify "Analyserar ${base_name}..." "Kör GROBID + Crossref"

  bib_file="${pdf_file%.*}.bib"

  if python3 "$PDF2ZOTERO_PY" "$pdf_file"; then
    if [ -f "$bib_file" ]; then
      log_info "Skickar ${bib_file} till Zotero..."
      open -a Zotero "$bib_file"
      log_step "Klart! '${base_name}' är öppnad i Zotero. Kontrollera att PDF:en sitter som bifogad fil."
      notify "Klar! Öppnad i Zotero — kontrollera PDF-bilagan:" "${base_name}"
    else
      alert_error "Kunde inte hitta genererad BibTeX-fil för ${base_name}"
      failed=$((failed + 1))
    fi
  else
    alert_error "pdf2zotero misslyckades för ${base_name}"
    failed=$((failed + 1))
  fi
done

if [ "$failed" -gt 0 ]; then
  exit 1
fi
