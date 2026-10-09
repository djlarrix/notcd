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
# Va todo dentro de funciones y sin `exit`: con `irm | iex`, un `exit` cerraria la
# ventana de PowerShell de la persona y no alcanzaria a leer el error.

# ---------------------------------------------------------------- utilidades

$script:ErrorEnUso = 'os error 32|os error 5|being used by another process|siendo utilizado por otro proceso|Access is denied|Acceso denegado'

function Paso($n, $texto) { Write-Host ''; Write-Host "[$n/5] $texto" -ForegroundColor White }
function Ok($texto) { Write-Host "      $texto" -ForegroundColor DarkGray }
function Malo($texto) { Write-Host "      $texto" -ForegroundColor Red }
function Atencion($texto) { Write-Host "      $texto" -ForegroundColor Yellow }

# Que programas tienen abiertos estos archivos. Usa el Administrador de reinicio de
# Windows (el mismo que usan los instaladores para decir "cierra tal programa").
$CodigoBloqueos = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class NotcdBloqueos {
    [StructLayout(LayoutKind.Sequential)]
    struct UNICO { public int Pid; public System.Runtime.InteropServices.ComTypes.FILETIME Inicio; }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct INFO {
        public UNICO Proceso;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string Nombre;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)] public string Servicio;
        public int Tipo; public uint Estado; public uint Sesion;
        [MarshalAs(UnmanagedType.Bool)] public bool Reiniciable;
    }
    [DllImport("rstrtmgr.dll", CharSet = CharSet.Unicode)] static extern int RmStartSession(out uint s, int f, string k);
    [DllImport("rstrtmgr.dll")] static extern int RmEndSession(uint s);
    [DllImport("rstrtmgr.dll", CharSet = CharSet.Unicode)] static extern int RmRegisterResources(uint s, uint n, string[] a, uint na, UNICO[] p, uint ns, string[] sv);
    [DllImport("rstrtmgr.dll")] static extern int RmGetList(uint s, out uint necesarios, ref uint n, [In, Out] INFO[] info, ref uint razones);
    public static List<string> Quien(string[] archivos) {
        var salida = new List<string>();
        uint s;
        if (archivos.Length == 0 || RmStartSession(out s, 0, Guid.NewGuid().ToString()) != 0) return salida;
        try {
            if (RmRegisterResources(s, (uint)archivos.Length, archivos, 0, null, 0, null) != 0) return salida;
            uint necesarios = 0, n = 0, razones = 0;
            if (RmGetList(s, out necesarios, ref n, null, ref razones) != 234 || necesarios == 0) return salida;
            var info = new INFO[necesarios];
            n = necesarios;
            if (RmGetList(s, out necesarios, ref n, info, ref razones) != 0) return salida;
            for (int i = 0; i < n; i++) {
                string ruta = "";
                try { ruta = System.Diagnostics.Process.GetProcessById(info[i].Proceso.Pid).MainModule.FileName; } catch { }
                salida.Add(info[i].Nombre + "|" + info[i].Proceso.Pid + "|" + ruta);
            }
        } finally { RmEndSession(s); }
        return salida;
    }
}
'@

function Get-ProcesosQueBloquean([string[]]$Carpetas) {
    # Lista "nombre|pid|ruta" de los programas que tienen abiertos ejecutables o
    # bibliotecas dentro de esas carpetas.
    if (-not ('NotcdBloqueos' -as [type])) { Add-Type -TypeDefinition $CodigoBloqueos -ErrorAction SilentlyContinue }
    $archivos = @(foreach ($c in $Carpetas) {
        if ($c -and (Test-Path $c)) {
            Get-ChildItem -Path $c -Recurse -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Extension -in '.exe', '.dll', '.pyd' } | ForEach-Object { $_.FullName }
        }
    })
    if ($archivos.Count -eq 0) { return @() }
    return @([NotcdBloqueos]::Quien([string[]]$archivos))
}

function Stop-ProcesosPropios($Anterior) {
    # El conector de notcd (o el de la version anterior, que tenia otro nombre) y el
    # navegador de su inicio de sesion. Solo procesos de esta sesion de Windows.
    $sesion = (Get-Process -Id $PID).SessionId
    $patron = "-m ($Anterior|notcd) |\\\.($Anterior|notcd)\\|\\uv\\tools\\($Anterior|notcd)\\"
    $propios = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.SessionId -eq $sesion -and $_.ProcessId -ne $PID -and
        (($_.CommandLine -match $patron) -or ($_.ExecutablePath -match $patron))
    })
    foreach ($p in $propios) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
    if ($propios.Count -gt 0) { Start-Sleep -Seconds 2 }
    return $propios.Count
}

function Explicar-Error($Salida, $Carpetas) {
    # Traduce el error de uv a algo que se pueda resolver.
    Write-Host ''
    Malo 'No se pudo instalar notcd. El error fue:'
    ($Salida -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -Last 8) | ForEach-Object { Write-Host "        $_" -ForegroundColor DarkGray }
    Write-Host ''
    if ($Salida -match 'certificate|certificado|UnknownIssuer|invalid peer|handshake') {
        Atencion 'La red de tu oficina revisa las conexiones seguras y uv no confia en ella.'
        Atencion 'Pide al equipo de TI que permita pypi.org, files.pythonhosted.org y github.com,'
        Atencion 'o prueba desde otra red (por ejemplo, el telefono como punto de acceso).'
    } elseif ($Salida -match $script:ErrorEnUso) {
        $quien = @(Get-ProcesosQueBloquean $Carpetas)
        if ($quien.Count -gt 0) {
            Atencion 'Estos programas tienen tomados archivos de notcd:'
            foreach ($q in $quien) {
                $partes = $q -split '\|'
                Atencion "  - $($partes[0]) (proceso $($partes[1])) $($partes[2])"
            }
            if ($quien -match 'MsMpEng|Defender|antimalware|antivirus|Sophos|CrowdStrike|Cylance|SentinelOne|McAfee|Symantec|ESET|Kaspersky') {
                Atencion 'Es el antivirus revisando los archivos nuevos: espera un minuto y vuelve a pegar el comando.'
                Atencion 'Si se repite, pide a TI que excluya la carpeta %APPDATA%\uv del analisis en tiempo real.'
            } else {
                Atencion 'Cierra esos programas (la app del asistente: icono junto al reloj, Salir) y vuelve a pegar el comando.'
            }
        } else {
            Atencion 'Windows bloqueo un archivo (suele ser el antivirus revisando lo recien descargado).'
            Atencion 'Espera un minuto y vuelve a pegar el comando.'
        }
    } elseif ($Salida -match 'dns error|failed to resolve|failed to connect|connection|timed out|tiempo de espera|proxy|network') {
        Atencion 'No hubo conexion con pypi.org o github.com. Revisa internet; si estas en la red de la'
        Atencion 'oficina, puede que el firewall los bloquee: prueba desde otra red o consulta a TI.'
    } else {
        Atencion 'Envia este mensaje a quien te ayuda con la instalacion.'
    }
    Atencion "El detalle completo quedo en: $script:Log"
}

# ------------------------------------------------------------------ instalacion

function Instalar-Notcd {
    # 'Continue': en PowerShell 5, con 'Stop', lo que un programa escribe en stderr se vuelve
    # un error fatal. Los programas se revisan por su codigo de salida; los cmdlets que no
    # pueden fallar llevan -ErrorAction Stop.
    $ErrorActionPreference = 'Continue'
    $ProgressPreference = 'SilentlyContinue'  # la barra de progreso hace lentisimas las descargas en PowerShell 5
    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

    $Repo = 'djlarrix/notcd'
    $Ref = if ($env:NOTCD_REF) { $env:NOTCD_REF } else { 'main' }
    $Casa = if ($env:NOTCD_HOME) { $env:NOTCD_HOME } else { Join-Path $env:USERPROFILE '.notcd' }
    $Anterior = 'not' + 'cl' + 'aude'  # la version anterior de este proyecto tenia otro nombre
    $script:Log = Join-Path $Casa 'instalacion.log'
    New-Item -ItemType Directory -Force -Path $Casa | Out-Null
    "notcd: instalacion $(Get-Date -Format s)" | Out-File -FilePath $script:Log -Encoding utf8

    # uv usa los certificados de Windows (las redes de oficina que revisan las conexiones
    # seguras ponen los suyos ahi) y copia en vez de enlazar archivos (menos choques con
    # el antivirus).
    $env:UV_NATIVE_TLS = '1'
    $env:UV_LINK_MODE = 'copy'

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
        powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex" 2>&1 |
            ForEach-Object { "$_" } | Out-File -FilePath $script:Log -Append -Encoding utf8
        $Uv = $UvLocal
        if (-not (Test-Path $Uv)) {
            Malo 'No se pudo instalar uv. Revisa la conexión a internet y vuelve a intentar.'
            Malo "Detalle en: $script:Log"
            return
        }
        Ok "Instalado: $(& $Uv --version)"
    }
    $DirHerramientas = (& $Uv tool dir 2>$null | Out-String).Trim()

    # ------------------------------------------------------ 2. notcd
    Paso 2 'Descargando e instalando notcd'
    # Cada descarga va a una carpeta nueva: nunca hay que mover ni borrar archivos que
    # otro programa (por ejemplo el antivirus) pueda tener abiertos.
    $Descargas = Join-Path $Casa 'fuente'
    $Destino = Join-Path $Descargas (Get-Date -Format 'yyyyMMdd-HHmmss')
    New-Item -ItemType Directory -Force -Path $Destino | Out-Null
    $Zip = Join-Path $Destino 'notcd.zip'
    try {
        Invoke-WebRequest -Uri "https://github.com/$Repo/archive/$Ref.zip" -OutFile $Zip -UseBasicParsing -ErrorAction Stop
        Expand-Archive -Path $Zip -DestinationPath $Destino -Force -ErrorAction Stop
    } catch {
        Malo "No se pudo descargar notcd desde github.com: $($_.Exception.Message)"
        Malo 'Revisa internet; en la red de la oficina, puede que el firewall bloquee github.com.'
        return
    }
    Remove-Item $Zip -Force -ErrorAction SilentlyContinue
    $Fuente = (Get-ChildItem -Path $Destino -Directory | Where-Object { $_.Name -like 'notcd-*' } | Select-Object -First 1).FullName
    Get-ChildItem -Path $Descargas -Directory | Where-Object { $_.FullName -ne $Destino } |
        ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
    Ok "Descargada la última versión de github.com/$Repo"

    # Al actualizar, Windows no deja reemplazar archivos en uso: se detiene el conector de
    # notcd si la app lo tenía abierto (la app lo vuelve a abrir al reiniciarse).
    if ((Stop-ProcesosPropios $Anterior) -gt 0) { Ok 'Se detuvo el conector de notcd que estaba en uso.' }
    if ((& $Uv tool list 2>$null | Out-String) -match "(?m)^$Anterior ") {
        & $Uv tool uninstall $Anterior 2>&1 | ForEach-Object { "$_" } | Out-File -FilePath $script:Log -Append -Encoding utf8
        if ($LASTEXITCODE -eq 0) { Ok 'Desinstalada la versión anterior' }
    }

    Ok 'Instalando componentes (la primera vez tarda uno o dos minutos)...'
    $CarpetasPropias = @((Join-Path $DirHerramientas 'notcd'), (Join-Path $env:USERPROFILE '.local\bin'))
    $instalado = $false
    for ($intento = 1; $intento -le 3; $intento++) {
        # "$_" convierte cada línea de stderr en su texto, sin el ruido que agrega PowerShell 5.
        $salida = (& $Uv tool install --force --upgrade --reinstall-package notcd --python 3.12 $Fuente 2>&1 |
            ForEach-Object { "$_" }) -join "`n"
        $codigo = $LASTEXITCODE
        $salida | Out-File -FilePath $script:Log -Append -Encoding utf8
        if ($codigo -eq 0) { $instalado = $true; break }
        if ($salida -notmatch $script:ErrorEnUso) { break }
        Ok "Un archivo estaba ocupado; reintentando ($intento de 3)..."
        Stop-ProcesosPropios $Anterior | Out-Null
        Start-Sleep -Seconds (8 * $intento)
    }
    if (-not $instalado) {
        Explicar-Error $salida $CarpetasPropias
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

# Con NOTCD_SOLO_FUNCIONES=1 sólo se cargan las funciones (para las pruebas).
if ($env:NOTCD_SOLO_FUNCIONES -ne '1') {
    try {
        Instalar-Notcd
    } catch {
        Write-Host ''
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host '  Revisa la conexión a internet y vuelve a pegar el comando.' -ForegroundColor Red
    }
}
