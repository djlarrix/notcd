# notcd - instalador para Windows. Un solo comando en PowerShell:
#
#   irm https://raw.githubusercontent.com/djlarrix/notcd/main/instalar.ps1 | iex
#
# Hace todo: instala uv (el gestor de Python) si falta, descarga notcd, lo
# instala, abre el inicio de sesion de Google, lo registra en la app de escritorio y
# en la app de codigo del asistente e instala la skill. Para actualizar, se pega el
# mismo comando.
#
# Opciones (variables de entorno, antes del comando):
#   $env:NOTCD_SIN_LOGIN = '1'     no abrir el inicio de sesion de Google
#   $env:NOTCD_SIN_DESKTOP = '1'   no registrar en la app de escritorio (solo en la de codigo)
#
# Va todo dentro de una funcion y sin `exit`: con `irm | iex`, un `exit` cerraria
# la ventana de PowerShell de la persona y no alcanzaria a leer el error.

function Instalar-Notcd {
    # 'Continue': en PowerShell 5, con 'Stop', lo que un programa escribe en stderr se vuelve
    # un error fatal. Los programas se revisan por su código de salida; los cmdlets que no
    # pueden fallar llevan -ErrorAction Stop.
    $ErrorActionPreference = 'Continue'
    $ProgressPreference = 'SilentlyContinue'  # la barra de progreso hace lentisimas las descargas en PowerShell 5
    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

    $Repo = 'djlarrix/notcd'
    $Ref = if ($env:NOTCD_REF) { $env:NOTCD_REF } else { 'main' }
    $Casa = if ($env:NOTCD_HOME) { $env:NOTCD_HOME } else { Join-Path $env:USERPROFILE '.notcd' }
    $Fuente = Join-Path $Casa 'fuente'

    function Paso($n, $texto) { Write-Host ''; Write-Host "[$n/5] $texto" -ForegroundColor White }
    function Ok($texto) { Write-Host "      $texto" -ForegroundColor DarkGray }
    function Malo($texto) { Write-Host "      $texto" -ForegroundColor Red }

    Write-Host ''
    Write-Host '  NOTCD' -ForegroundColor White
    Write-Host '  NotebookLM para el estudio' -ForegroundColor Cyan

    # ------------------------------------------------------------- 1. uv
    Paso 1 'Comprobando uv (instala y aísla Python para notcd)'
    $Uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
    $UvLocal = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
    if (-not $Uv -and (Test-Path $UvLocal)) { $Uv = $UvLocal }
    if ($Uv) {
        Ok "Ya está: $(& $Uv --version)"
    } else {
        Ok 'No está. Instalándolo desde astral.sh (el sitio oficial de uv)...'
        powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex" | Out-Null
        $Uv = $UvLocal
        if (-not (Test-Path $Uv)) {
            Malo 'No se pudo instalar uv. Revisa la conexión a internet y vuelve a intentar.'
            return
        }
        Ok "Instalado: $(& $Uv --version)"
    }

    # ------------------------------------------------------ 2. notcd
    Paso 2 'Descargando e instalando notcd'
    New-Item -ItemType Directory -Force -Path $Casa | Out-Null
    $Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ('notcd-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $Tmp -ErrorAction Stop | Out-Null
    $Zip = Join-Path $Tmp 'notcd.zip'
    Invoke-WebRequest -Uri "https://github.com/$Repo/archive/$Ref.zip" -OutFile $Zip -UseBasicParsing -ErrorAction Stop
    Expand-Archive -Path $Zip -DestinationPath $Tmp -Force -ErrorAction Stop
    $Carpeta = Get-ChildItem -Path $Tmp -Directory | Where-Object { $_.Name -like 'notcd-*' } | Select-Object -First 1
    if (Test-Path $Fuente) { Remove-Item -Recurse -Force $Fuente -ErrorAction Stop }
    Move-Item -Path $Carpeta.FullName -Destination $Fuente -ErrorAction Stop
    Remove-Item -Recurse -Force $Tmp
    Ok "Descargada la última versión de github.com/$Repo"

    # Al actualizar, Windows no deja reemplazar archivos en uso. Lo único de notcd que
    # puede estar en uso es su conector (python -m notcd servidor), que la app abre por
    # dentro: se detiene sólo ese proceso. La app lo vuelve a abrir al reiniciarse.
    # También el de la versión anterior, que tenía otro nombre.
    $Anterior = 'not' + 'cl' + 'aude'  # la version anterior de este proyecto tenia otro nombre
    $Sesion = (Get-Process -Id $PID).SessionId
    $EnUso = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.SessionId -eq $Sesion -and $_.Name -like 'python*.exe' -and
        $_.CommandLine -match "-m ($Anterior|notcd) (servidor|login)"
    })
    if ($EnUso.Count -gt 0) {
        Ok 'Deteniendo el conector de notcd que estaba en uso, para poder actualizarlo...'
        $EnUso | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 2
    }
    if ((& $Uv tool list 2>$null) -match "^$Anterior ") {
        & $Uv tool uninstall $Anterior *> $null
        if ($LASTEXITCODE -eq 0) { Ok 'Desinstalada la versión anterior' }
    }
    Ok 'Instalando componentes (la primera vez tarda uno o dos minutos)...'
    & $Uv tool install --quiet --force --upgrade --reinstall-package notcd --python 3.12 $Fuente
    if ($LASTEXITCODE -ne 0) {
        Malo 'No se pudo instalar notcd (algún archivo en uso). Reinicia el computador y vuelve a pegar el comando.'
        return
    }
    $Notcd = Join-Path (& $Uv tool dir --bin) 'notcd.exe'
    if (-not (Test-Path $Notcd)) { Malo "No quedó instalado el comando notcd ($Notcd)."; return }
    Ok "Instalado: $(& $Notcd --version)"

    # -------------------------------------------------------- 3. Google
    Paso 3 'Conectando con tu cuenta de Google (NotebookLM)'
    if ($env:NOTCD_SIN_LOGIN -eq '1') {
        Ok 'Omitido. Para conectar después:  notcd login'
    } else {
        & $Notcd estado *> $null
        if ($LASTEXITCODE -eq 0) {
            & $Notcd estado
        } else {
            & $Notcd login
            if ($LASTEXITCODE -ne 0) {
                Malo 'El inicio de sesión no terminó. Puedes reintentarlo después con:  notcd login'
                Malo 'o pidiéndole al asistente: «Conéctate a NotebookLM».'
            }
        }
    }

    # ---------------------------------------------------------- 4. Apps
    Paso 4 'Registrando notcd en la app de escritorio y en la app de código'
    if ($env:NOTCD_SIN_DESKTOP -eq '1') { & $Notcd configurar --sin-desktop } else { & $Notcd configurar --esperar }
    if ($LASTEXITCODE -ne 0) { Malo 'Hubo problemas al registrar; revisa los mensajes de arriba.' }

    # --------------------------------------------------------- 5. Listo
    Paso 5 'Listo'
    Write-Host ''
    Write-Host '      Abre la app de escritorio y pregúntale:' -ForegroundColor White
    Write-Host '      «¿Qué cuadernos tengo en NotebookLM?»' -ForegroundColor DarkGray
    Write-Host ''
    Write-Host '      Para actualizar más adelante, vuelve a pegar el mismo comando.' -ForegroundColor DarkGray
    Write-Host '      Si algo falla, en una ventana nueva de PowerShell:  notcd diagnostico' -ForegroundColor DarkGray
    Write-Host ''
}

try {
    Instalar-Notcd
} catch {
    Write-Host ''
    Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host '  Revisa la conexión a internet y vuelve a pegar el comando.' -ForegroundColor Red
}
