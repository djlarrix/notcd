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
    if ($Salida -match 'os error 4551|Control de aplicaciones|Application Control') {
        Atencion 'Windows (Control inteligente de aplicaciones) bloqueó un archivo sin firma digital.'
        Atencion 'notcd no debería usar nada sin firma: envía este mensaje (o el registro de abajo)'
        Atencion 'a quien te ayuda con la instalación, para corregirlo.'
    } elseif ($Salida -match 'certificate|certificado|UnknownIssuer|invalid peer|handshake') {
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

function Get-ControlApps {
    # Control inteligente de aplicaciones de Windows 11: 0 desactivado, 1 activado, 2 en evaluación.
    try {
        $v = (Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy' -Name VerifiedAndReputablePolicyState -ErrorAction Stop).VerifiedAndReputablePolicyState
        return [int]$v
    } catch { return 0 }
}

function Test-Firmado($Exe) {
    $firma = Get-AuthenticodeSignature -FilePath $Exe -ErrorAction SilentlyContinue
    return ($firma -and $firma.Status -eq 'Valid')
}

function Get-VersionPython($Exe) {
    $v = (& $Exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null | Out-String).Trim()
    return $v
}

function Find-PythonFirmado {
    # Un Python oficial (firmado digitalmente) ya instalado, de 3.10 a 3.14.
    $candidatos = @()
    $py = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
    if ($py) {
        foreach ($v in '3.12', '3.13', '3.11', '3.10', '3.14') {
            $ruta = (& $py "-$v" -c "import sys; print(sys.executable)" 2>$null | Out-String).Trim()
            if ($ruta) { $candidatos += $ruta }
        }
    }
    foreach ($base in @((Join-Path $env:LOCALAPPDATA 'Programs\Python'), $env:ProgramFiles)) {
        if ($base -and (Test-Path $base)) {
            $candidatos += @(Get-ChildItem -Path $base -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue |
                ForEach-Object { Join-Path $_.FullName 'python.exe' })
        }
    }
    foreach ($c in ($candidatos | Select-Object -Unique)) {
        # El python.exe de WindowsApps es un acceso directo a la tienda, no un Python.
        if (-not (Test-Path $c) -or $c -match '\\WindowsApps\\') { continue }
        if ((Get-VersionPython $c) -notin '3.10', '3.11', '3.12', '3.13', '3.14') { continue }
        if (Test-Firmado $c) { return $c }
    }
    return $null
}

function Install-PythonOficial {
    # Python 3.12 oficial de python.org, sólo para este usuario (sin permisos de
    # administrador). Antes de ejecutarlo se comprueba que lo firma la Python Software
    # Foundation.
    $version = '3.12.10'
    $arq = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
    $instalador = Join-Path $env:TEMP "python-$version-$arq.exe"
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/$version/python-$version-$arq.exe" -OutFile $instalador -UseBasicParsing -ErrorAction Stop
    $firma = Get-AuthenticodeSignature -FilePath $instalador
    if ($firma.Status -ne 'Valid' -or $firma.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
        Remove-Item $instalador -Force -ErrorAction SilentlyContinue
        throw 'El instalador de Python descargado no tiene una firma válida de la Python Software Foundation.'
    }
    $opciones = '/quiet', 'InstallAllUsers=0', 'PrependPath=0', 'Include_launcher=0', 'Include_test=0',
        'Include_doc=0', 'Include_tcltk=0', 'Shortcuts=0', 'AssociateFiles=0'
    $proceso = Start-Process -FilePath $instalador -ArgumentList $opciones -Wait -PassThru
    Remove-Item $instalador -Force -ErrorAction SilentlyContinue
    if ($proceso.ExitCode -ne 0) { throw "El instalador de Python terminó con el código $($proceso.ExitCode)." }
    $exe = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if (-not (Test-Path $exe)) { throw "Python no quedó en $exe." }
    return $exe
}

function Add-RutaUsuario($Carpeta) {
    # Que el comando notcd se encuentre en ventanas nuevas de PowerShell.
    $actual = [Environment]::GetEnvironmentVariable('Path', 'User')
    if (-not (($actual -split ';') -contains $Carpeta)) {
        [Environment]::SetEnvironmentVariable('Path', ($(if ($actual) { "$actual;" } else { '' }) + $Carpeta), 'User')
    }
    if (-not (($env:Path -split ';') -contains $Carpeta)) { $env:Path = "$env:Path;$Carpeta" }
}

# ------------------------------------------------------------------ instalacion

function Instalar-Notcd {
    # 'Continue': en PowerShell 5, con 'Stop', lo que un programa escribe en stderr se vuelve
    # un error fatal. Los programas se revisan por su codigo de salida; los cmdlets que no
    # pueden fallar llevan -ErrorAction Stop.
    $ErrorActionPreference = 'Continue'
    $ProgressPreference = 'SilentlyContinue'  # la barra de progreso hace lentisimas las descargas en PowerShell 5
    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
    $env:PYTHONUTF8 = '1'  # que Python escriba sus mensajes en UTF-8 (si no, salen acentos rotos)

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
    $env:UV_SYSTEM_CERTS = '1'
    $env:UV_LINK_MODE = 'copy'

    Write-Host ''
    Write-Host '  NOTCD' -ForegroundColor White
    Write-Host '  NotebookLM para el estudio' -ForegroundColor Cyan

    # ------------------------------------------------------- 1. Python y uv
    Paso 1 'Preparando Python (el oficial, con firma digital) y uv'
    # Windows bloquea los programas sin firma digital cuando está activo el Control
    # inteligente de aplicaciones (y puede activarse más adelante). Por eso notcd corre
    # siempre sobre el Python oficial de python.org, que viene firmado.
    $control = Get-ControlApps
    if ($control -eq 1) { Ok 'Control inteligente de aplicaciones: activado (por eso se usa el Python oficial firmado).' }
    elseif ($control -eq 2) { Ok 'Control inteligente de aplicaciones: en evaluación.' }
    $PythonBase = if ($env:NOTCD_DESCARGAR_PYTHON -eq '1') { $null } else { Find-PythonFirmado }
    if ($PythonBase) {
        Ok "Python oficial: ya está ($PythonBase)"
    } else {
        Ok 'Python oficial: no está. Instalándolo desde python.org (uno o dos minutos)...'
        try { $PythonBase = Install-PythonOficial } catch {
            Malo "No se pudo instalar Python: $($_.Exception.Message)"
            Malo 'Revisa internet; en la red de la oficina, puede que el firewall bloquee python.org.'
            return
        }
        Ok "Python oficial: instalado ($PythonBase)"
    }

    $Uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
    $UvLocal = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
    if (-not $Uv -and (Test-Path $UvLocal)) { $Uv = $UvLocal }
    if (-not $Uv) {
        Ok 'uv: no está. Instalándolo desde astral.sh (el sitio oficial de uv)...'
        powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex" 2>&1 |
            ForEach-Object { "$_" } | Out-File -FilePath $script:Log -Append -Encoding utf8
        $Uv = $UvLocal
        if (-not (Test-Path $Uv)) {
            Malo 'No se pudo instalar uv. Revisa la conexión a internet y vuelve a intentar.'
            Malo "Detalle en: $script:Log"
            return
        }
    }
    Ok "uv: $(& $Uv --version)"

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
    # Instalaciones anteriores con uv tool (la versión anterior y las primeras de notcd)
    # dejaban lanzadores .exe sin firma: se quitan.
    $herramientas = (& $Uv tool list 2>$null | Out-String)
    foreach ($vieja in @($Anterior, 'notcd')) {
        if ($herramientas -match "(?m)^$vieja ") {
            & $Uv tool uninstall $vieja 2>&1 | ForEach-Object { "$_" } | Out-File -FilePath $script:Log -Append -Encoding utf8
            if ($vieja -eq $Anterior -and $LASTEXITCODE -eq 0) { Ok 'Desinstalada la versión anterior' }
        }
    }

    # El entorno de notcd: un entorno virtual del Python oficial. Su python.exe es el
    # lanzador oficial, también firmado.
    $Entorno = Join-Path $Casa 'entorno'
    $Py = Join-Path $Entorno 'Scripts\python.exe'
    $recrear = -not (Test-Path $Py)
    if (-not $recrear) {
        $cfg = Join-Path $Entorno 'pyvenv.cfg'
        $home_ = if (Test-Path $cfg) { ((Get-Content $cfg | Where-Object { $_ -match '^home\s*=' }) -replace '^home\s*=\s*', '').Trim() } else { '' }
        $recrear = -not ($home_ -and (Test-Path (Join-Path $home_ 'python.exe')) -and (Test-Firmado (Join-Path $home_ 'python.exe')))
    }
    # Desde la 0.3.0 notcd no usa nada compilado. Un entorno con bibliotecas compiladas (de
    # una versión anterior o de un intento bloqueado por Windows) se rehace desde cero.
    $SitePackages = Join-Path $Entorno 'Lib\site-packages'
    if (-not $recrear -and (Test-Path $SitePackages)) {
        $recrear = [bool](Get-ChildItem $SitePackages -Recurse -Include *.pyd, *.dll -File -ErrorAction SilentlyContinue | Select-Object -First 1)
    }
    if ($recrear) {
        if (Test-Path $Entorno) { Remove-Item $Entorno -Recurse -Force -ErrorAction SilentlyContinue }
        & $PythonBase -m venv $Entorno 2>&1 | ForEach-Object { "$_" } | Out-File -FilePath $script:Log -Append -Encoding utf8
        if (-not (Test-Path $Py)) {
            Malo 'No se pudo crear el entorno de Python de notcd.'
            Malo "Detalle en: $script:Log"
            return
        }
    }

    Ok 'Instalando componentes (la primera vez tarda uno o dos minutos)...'
    $instalado = $false
    for ($intento = 1; $intento -le 3; $intento++) {
        # "$_" convierte cada línea de stderr en su texto, sin el ruido que agrega PowerShell 5.
        $salida = (& $Uv pip install --python $Py --upgrade --reinstall-package notcd $Fuente 2>&1 |
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
        Explicar-Error $salida @($Entorno)
        return
    }
    # Cargar de verdad notcd: si Windows bloqueara algo, se sabe ahora y no cuando la app
    # intente abrir el conector.
    $prueba = (& $Py -c "import notcd.server, notcd.navegador, notebooklm; import notcd; print(notcd.__version__)" 2>&1 |
        ForEach-Object { "$_" }) -join "`n"
    $prueba | Out-File -FilePath $script:Log -Append -Encoding utf8
    if ($LASTEXITCODE -ne 0) {
        Explicar-Error $prueba @($Entorno)
        return
    }
    Ok "Instalado: notcd $(($prueba -split "`n")[-1].Trim())"

    # El comando notcd para la terminal: un .cmd que llama al Python firmado (los
    # lanzadores .exe que generan las herramientas de Python no tienen firma).
    $Bin = Join-Path $env:USERPROFILE '.local\bin'
    New-Item -ItemType Directory -Force -Path $Bin | Out-Null
    # %USERPROFILE% en vez de la ruta escrita: un .cmd no tolera tildes en las rutas.
    $PyCmd = if ($Py.StartsWith($env:USERPROFILE)) { '%USERPROFILE%' + $Py.Substring($env:USERPROFILE.Length) } else { $Py }
    Set-Content -Path (Join-Path $Bin 'notcd.cmd') -Encoding ascii -Value "@echo off`r`n`"$PyCmd`" -m notcd %*"
    Add-RutaUsuario $Bin

    # -------------------------------------------------------- 3. Google
    Paso 3 'Conectando con tu cuenta de Google (NotebookLM)'
    if ($env:NOTCD_SIN_LOGIN -eq '1') {
        Ok 'Omitido. Para conectar después:  notcd login'
    } else {
        & $Py -m notcd estado *> $null
        if ($LASTEXITCODE -eq 0) {
            & $Py -m notcd estado
        } else {
            & $Py -m notcd login
            if ($LASTEXITCODE -ne 0) {
                Malo 'El inicio de sesión no terminó. Puedes reintentarlo después con:  notcd login'
                Malo 'o pidiéndole al asistente: «Conéctate a NotebookLM».'
            }
        }
    }

    # ---------------------------------------------------------- 4. Apps
    Paso 4 'Registrando notcd en la app de escritorio y en la app de código'
    if ($env:NOTCD_SIN_DESKTOP -eq '1') { & $Py -m notcd configurar --sin-desktop } else { & $Py -m notcd configurar --esperar }
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
