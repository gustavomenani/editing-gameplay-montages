"""Diagnóstico da instalação: uma linha por verificação, no fim PRONTO ou FALTA: ... com o que fazer. Código de saída 0 / 1.

uso (na pasta do projeto, ou em qualquer pasta; a pasta onde roda é a que vai guardar o projeto):
    $PY doctor.py                 (PY=./venv311/Scripts/python)

Verifica: Python (3.11, venv) e os pacotes do requirements.txt (numpy, cv2, scipy, PIL, binding do RIFE), ffmpeg / ffprobe
(versão e um encode de verdade que grava na pasta), a pasta do modelo do RIFE, uma chamada real do RIFE na GPU (cronometrada;
mostra RIFE_GPU e a lista de dispositivos Vulkan), a fonte Impact, espaço livre em disco, permissão de escrita na pasta
(OneDrive, "Acesso controlado a pastas" do Defender) e acentos no caminho. Não instala nem altera nada: só grava e apaga
arquivos de teste (.doctor_*) na pasta.

O teste do RIFE roda num processo filho (o runtime Vulkan pode travar ou derrubar o processo; aqui só o filho cai) com
rifeutil.load(), o mesmo caminho dos scripts. Ele respeita RIFE_GPU e RIFE_MODEL do ambiente.
Status: OK, AVISO (funciona, mas vale saber) e FALTA (o pipeline não roda assim)."""
import importlib, importlib.metadata as md, importlib.util, json, os, re, shutil, subprocess, sys, tempfile, time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")      # acentos também quando a saída é um pipe (cp1252 por padrão no Windows)
except (AttributeError, ValueError):
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
NEED_GB = 13.0           # edit de 30 s: 7 GB (estilo da casa) a 13 GB (estilo da referência, 1080p largo) de store, mais o master
MIN_GB = 7.0
MODEL = "rife-v4.25"
LAYOUT = ("rife-v2", "rife-v3", "rife-v4", "rife4", "rife-4")      # igual a rifeutil.LAYOUT
FIX_VENV = "uv venv --python 3.11 venv311  e depois  uv pip install --python venv311/Scripts/python.exe -r requirements.txt"
FIX_PIP = "uv pip install --python venv311/Scripts/python.exe -r requirements.txt"
rows = []                # (status, text, fix)


def num(x, d=1):
    return ("%.*f" % (d, x)).replace(".", ",")


def add(status, text, fix=None, short=None):
    rows.append((status, text, fix, short or re.split(r": | \(", text)[0]))
    print("%-7s %s" % ("[" + status + "]", text), flush=True)


def tail(text, n=300):
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n] + "..."


# ---------------------------------------------------------------- Python e pacotes
def check_python():
    v = sys.version_info
    venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    where = ("venv: " + sys.prefix) if venv else "fora de um venv: " + sys.executable
    if (v.major, v.minor) == (3, 11):
        if venv:
            add("OK", f"Python {v.major}.{v.minor}.{v.micro} ({where})")
        else:
            add("AVISO", f"Python {v.major}.{v.minor}.{v.micro}, mas {where}",
                "este não parece ser o Python do projeto: rode com PY=./venv311/Scripts/python (pipeline.md, Setup)")
    else:
        add("AVISO", f"Python {v.major}.{v.minor}.{v.micro} ({where}); o binding do RIFE só tem pacotes para o 3.11",
            "crie o venv com o 3.11:  " + FIX_VENV)


def pins():
    out = {}
    try:
        for line in open(os.path.join(HERE, "requirements.txt"), encoding="utf-8"):
            m = re.match(r"\s*([A-Za-z0-9_.-]+)==([^\s#]+)", line)
            if m:
                out[m.group(1).lower().replace("_", "-")] = m.group(2)
    except OSError:
        pass
    return out


def dist_version(names):
    for n in names:
        try:
            return md.version(n)
        except md.PackageNotFoundError:
            continue
    return None


def check_packages():
    pin = pins()
    missing = []
    for label, module, dists, always in (("numpy", "numpy", ["numpy"], True), ("cv2 (OpenCV)", "cv2", ["opencv-python", "opencv-python-headless"], True),
                                         ("scipy", "scipy", ["scipy"], True), ("PIL (Pillow)", "PIL", ["pillow"], True),
                                         ("rife-ncnn-vulkan-python", "rife_ncnn_vulkan_python", ["rife-ncnn-vulkan-python-tntwise"], True)):
        ver = dist_version(dists)
        try:
            if module == "rife_ncnn_vulkan_python":
                ok = importlib.util.find_spec(module) is not None       # só localiza: o import de verdade acontece no teste do RIFE (carrega a DLL do Vulkan)
                err = "não encontrado"
            else:
                importlib.import_module(module)
                ok, err = True, ""
        except Exception as e:                                          # ImportError, DLL load failed, versão do numpy incompatível...
            ok, err = False, "não instalado" if isinstance(e, ModuleNotFoundError) else f"{type(e).__name__}: {tail(str(e), 160)}"
        if not ok:
            missing.append(label)
            add("FALTA", f"pacote {label}: {err}", "instale os pacotes no venv do projeto:  " + FIX_PIP + "  (Python 3.11)")
            continue
        want = pin.get(dists[0])
        if want and ver and ver != want:
            add("AVISO", f"pacote {label} {ver} (a skill foi testada com {want})", "para a versão testada:  " + FIX_PIP)
        else:
            add("OK", f"pacote {label} {ver or '?'}")
    return not missing


# ---------------------------------------------------------------- ffmpeg
def check_ffmpeg(folder):
    sys.path.insert(0, HERE)
    try:
        import ff
        exe, probe = ff.FF, ff.FFPROBE
    except SystemExit as e:
        ff_env = (os.environ.get("FF") or "").strip()
        add("FALTA", "ffmpeg/ffprobe não encontrados (" + (f"FF={ff_env} não existe e " if ff_env else "") + "não estão no PATH nem nas pastas do winget/scoop/chocolatey)",
            "instale o ffmpeg:  winget install Gyan.FFmpeg  (depois feche e abra o terminal), ou aponte FF para o ffmpeg.exe", "ffmpeg/ffprobe não encontrados")
        return
    except Exception as e:
        add("FALTA", f"ffmpeg: {type(e).__name__}: {tail(str(e), 160)}", "winget install Gyan.FFmpeg")
        return
    try:
        v = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=30).stdout.splitlines()[0]
        vp = subprocess.run([probe, "-version"], capture_output=True, text=True, timeout=30).stdout.splitlines()[0]
    except (OSError, IndexError, subprocess.TimeoutExpired) as e:
        add("FALTA", f"ffmpeg em {exe} não executa ({type(e).__name__})", "reinstale:  winget install Gyan.FFmpeg")
        return
    ver = " ".join(v.split()[:3])
    add("OK", f"ffmpeg: {ver} ({exe})")
    add("OK", "ffprobe: " + " ".join(vp.split()[:3]))
    out = os.path.join(folder, ".doctor_ffmpeg.mp4")
    r = None
    try:
        r = subprocess.run([exe, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30", "-f", "lavfi", "-i", "sine=frequency=440",
                            "-frames:v", "10", "-shortest", "-c:v", "libx264", "-c:a", "aac", out], capture_output=True, text=True, timeout=60)
        good = r.returncode == 0 and os.path.getsize(out) > 0
    except (OSError, subprocess.TimeoutExpired):
        good = False
    finally:
        try:
            os.remove(out)
        except OSError:
            pass
    if good:
        add("OK", "ffmpeg codifica H.264 + AAC e grava nesta pasta")
    else:
        why = tail(r.stderr if r else "não terminou", 200)
        if re.search(r"Unknown encoder|Encoder .* not found", why):
            add("FALTA", f"este ffmpeg não tem libx264/aac ({why})", "instale a versão completa:  winget install Gyan.FFmpeg")
        elif "Permission denied" in why:
            add("FALTA", "o ffmpeg não tem permissão para gravar nesta pasta",
                "'Acesso controlado a pastas' do Windows ou o OneDrive: use uma pasta fora de Documentos/Imagens/Vídeos/Desktop (ex.: C:/Editor), ou libere o ffmpeg.exe e o python.exe nessa proteção")
        else:
            add("FALTA", f"o ffmpeg não conseguiu gravar um mp4 de teste aqui: {why}", "veja a mensagem do ffmpeg; se for de permissão, use uma pasta como C:/Editor", "ffmpeg não gravou o teste")
    try:
        f = subprocess.run([exe, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=30).stdout
        if " zscale " not in f or " tonemap " not in f:
            add("AVISO", "este ffmpeg não tem os filtros zscale/tonemap (só faz falta para clipes HDR)", "winget install Gyan.FFmpeg  (a versão 'full')")
    except (OSError, subprocess.TimeoutExpired):
        pass


# ---------------------------------------------------------------- RIFE
def model_candidates():
    env = os.environ.get("RIFE_MODEL")
    if env:
        return env, [env]
    return None, [f"models/{MODEL}", f"dl_rife_models/{MODEL}", os.path.expanduser(f"~/.claude/skills/editing-gameplay-montages/models/{MODEL}")]


def check_model():
    """-> caminho absoluto da pasta do modelo, ou None. Mesmas regras de rifeutil.model_dir, sem encerrar o processo."""
    env, cands = model_candidates()
    for c in cands:
        if os.path.exists(os.path.join(c, "flownet.bin")):
            break
    else:
        if env:
            add("FALTA", f"RIFE_MODEL={env} não tem flownet.bin", f"RIFE_MODEL deve ser a própria pasta do modelo (.../models/{MODEL}); apague a variável para usar ./models/{MODEL}", "RIFE_MODEL inválido")
        else:
            add("FALTA", f"modelo do RIFE não encontrado (procurei: {', '.join(os.path.abspath(c) for c in cands)})",
                f"copie a pasta models da skill para a pasta do projeto:  cp -r ~/.claude/skills/editing-gameplay-montages/models .  (mantenha o nome {MODEL})")
        return None
    path = os.path.abspath(c)
    binp, parp = os.path.join(path, "flownet.bin"), os.path.join(path, "flownet.param")
    if not os.path.exists(parp):
        add("FALTA", f"{path}: tem flownet.bin mas falta flownet.param (pasta incompleta)", "copie a pasta models da skill de novo", "modelo do RIFE incompleto")
        return None
    sb, sp = os.path.getsize(binp), os.path.getsize(parp)
    if sb < 1_000_000 or sp < 1000:
        add("FALTA", f"{path}: arquivos do modelo truncados (flownet.bin {sb} bytes, flownet.param {sp} bytes)", "copie a pasta models da skill de novo (o git pode ter estragado: clone de novo)", "modelo do RIFE truncado")
        return None
    if not any(t in path.replace("\\", "/") for t in LAYOUT):
        add("FALTA", f"{path}: o nome da pasta não tem a versão do RIFE (rife-v4.25...) e o binding lê o formato da rede por ele",
            f"renomeie a pasta para {MODEL}", "pasta do modelo com nome errado")
        return None
    add("OK", f"modelo do RIFE: {path} (flownet.bin {num(sb / 2**20)} MB)")
    return path


CHILD = "--rife-filho"


def child_main(model):
    """Roda no processo filho: carrega o RIFE, faz UMA interpolação 1920x1080 e imprime uma linha JSON."""
    sys.path.insert(0, HERE)
    os.environ["RIFE_MODEL"] = model
    import numpy as np
    import rifeutil
    t0 = time.time()
    rife = rifeutil.load()
    t_load = time.time() - t0
    H, W = 1080, 1920
    yy, xx = np.mgrid[0:H, 0:W]
    base = np.stack([(xx * 255 // W), (yy * 255 // H), ((xx + yy) * 255 // (W + H))], -1).astype(np.uint8)
    a, b = base.copy(), base.copy()
    a[400:700, 600:900] = (255, 40, 40)
    b[400:700, 680:980] = (255, 40, 40)                       # o quadrado anda 80 px: o quadro do meio o tem em 640..940
    t0 = time.time()
    out = rife.process_cv2(a, b, 0.5)
    t_call = time.time() - t0
    err = float(np.abs(out.astype(np.int16) - ((a.astype(np.int16) + b.astype(np.int16)) // 2)).mean())
    box = float(np.abs(out[400:700, 640:940].astype(np.int16) - np.array((255, 40, 40))).mean())    # no meio, o quadrado deve estar em 640..940
    print(json.dumps(dict(load=t_load, call=t_call, shape=list(out.shape), err=err, box=box, mean=float(out.mean()), gpu=os.environ.get("RIFE_GPU", "0"))), flush=True)
    rifeutil.finish(0)


def check_rife(model):
    if model is None:
        add("FALTA", "teste do RIFE não feito: sem a pasta do modelo")
        return
    if importlib.util.find_spec("rife_ncnn_vulkan_python") is None or importlib.util.find_spec("numpy") is None:
        add("FALTA", "teste do RIFE não feito: pacotes faltando (acima)")
        return
    gpu = os.environ.get("RIFE_GPU", "0").strip() or "0"
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, os.path.abspath(__file__), CHILD, model], capture_output=True, text=True, timeout=300,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        add("FALTA", f"o RIFE não respondeu em 300 s (RIFE_GPU={gpu}): driver de vídeo travado?",
            "atualize o driver da placa (site da NVIDIA/AMD/Intel), reinicie o PC; sem placa usável, RIFE_GPU=-1 roda na CPU (muito mais lento)")
        return
    devs = re.findall(r"^\[(\d+) (.+?)\]\s+queueC", r.stderr, re.M)
    devtxt = ", ".join(f"{i} = {n}" for i, n in devs) if devs else "nenhum dispositivo Vulkan listado"
    res = None
    for line in r.stdout.splitlines()[::-1]:
        if line.startswith("{"):
            try:
                res = json.loads(line)
            except ValueError:
                pass
            break
    if res is None:
        msg = " ".join(l for l in r.stderr.splitlines() if not re.match(r"^\[\d+ .+?\]\s+\w+=", l)).strip()
        if r.returncode not in (0, 1):
            msg = (msg + f" (o processo terminou com o código {r.returncode}: o driver Vulkan derrubou o RIFE)").strip()
        if not msg:
            msg = "sem mensagem (código %s)" % r.returncode
        if "No Vulkan GPU" in msg:
            add("FALTA", f"nenhuma GPU Vulkan utilizável (RIFE_GPU={gpu}); dispositivos: {devtxt}",
                "instale/atualize o driver da placa no site da NVIDIA, AMD ou Intel (não o driver básico do Windows) e reinicie; "
                "sem placa: RIFE_GPU=-1 roda na CPU, ~15 vezes mais lento (um edit de 30 s leva 10 a 17 horas)", "sem GPU Vulkan")
        elif "is not a number" in msg:
            add("FALTA", f"RIFE_GPU={gpu!r} não é um número", "RIFE_GPU é o número do dispositivo Vulkan (0, 1, ...) ou -1 para a CPU: apague a variável ou corrija o valor")
        elif f"RIFE_GPU={gpu}, but" in msg:
            ok = ("RIFE_GPU=" + ("0" if len(devs) == 1 else "um destes: " + ", ".join(i for i, _ in devs))) if devs else "RIFE_GPU=-1"
            add("FALTA", f"RIFE_GPU={gpu} não existe: o Vulkan achou {len(devs)} GPU(s): {devtxt}",
                f"apague a variável RIFE_GPU ou use {ok}; RIFE_GPU=-1 roda na CPU (~15x mais lento)")
        elif "DLL" in msg:
            add("FALTA", f"o binding do RIFE não carrega a DLL: {tail(msg, 240)}",
                "instale o Microsoft Visual C++ Redistributable (x64) em microsoft.com (ou: winget install Microsoft.VCRedist.2015+.x64) e atualize o driver da placa", "DLL do RIFE")
        else:
            add("FALTA", f"o RIFE falhou (RIFE_GPU={gpu}): {tail(msg, 300)}",
                "veja a mensagem; se for a GPU, atualize o driver e reinicie; RIFE_GPU=-1 roda na CPU (~15x mais lento)", "RIFE falhou")
        return
    cpu = gpu in ("-1", "cpu")
    bad = res["shape"] != [1080, 1920, 3] or res["mean"] < 5 or res["err"] > 20 or res["box"] > 60
    desc = f"RIFE_GPU={gpu}, dispositivos Vulkan: {devtxt}; carregar {num(res['load'])} s, 1 chamada 1920x1080 em {num(res['call'], 2)} s"
    if bad:
        add("FALTA", f"o RIFE rodou mas devolveu um quadro errado (erro médio {num(res['err'])}, quadrado {num(res['box'])}): {desc}",
            "driver de vídeo com defeito: atualize ou reinstale o driver; teste outra GPU com RIFE_GPU=1; RIFE_GPU=-1 usa a CPU", "RIFE devolveu quadro errado")
    elif cpu:
        add("AVISO", f"RIFE na CPU ({desc}): cerca de {num(res['call'] * 20000 / 3600)} h só de interpolação para um edit de 30 s",
            "com uma GPU Vulkan o mesmo edit leva ~1 h; apague RIFE_GPU=-1 se a placa funciona", "RIFE na CPU")
    else:
        sel = dict(devs).get(gpu, "?")
        add("OK", f"RIFE na GPU {gpu} ({sel}) — {desc}")
        igpu = re.search(r"Intel|UHD|Iris|Radeon\(TM\) Graphics|Vega|Microsoft Basic|llvmpipe|SwiftShader", sel, re.I)
        if len(devs) > 1 and igpu:
            others = ", ".join(f"{i} = {n}" for i, n in devs if i != gpu)
            add("AVISO", f"a GPU {gpu} ({sel}) parece integrada e há outra: {others}", f"use a dedicada:  RIFE_GPU={[i for i, _ in devs if i != gpu][0]}")
        elif res["call"] > 2.0:
            add("AVISO", f"1 chamada levou {num(res['call'])} s: é lento para uma GPU (uma GTX 1650 faz em ~0,1 s)",
                "confira se o RIFE usou a placa certa (RIFE_GPU) e se o driver está em dia")


# ---------------------------------------------------------------- fonte, disco, pasta
def check_font(folder):
    cands = [os.environ.get("IMPACT_FONT") or "", os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "impact.ttf"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts", "impact.ttf")]
    hit = next((c for c in cands if c and os.path.isfile(c)), None)
    if hit:
        add("OK", f"fonte Impact: {hit}")
        return
    ref = os.path.exists(os.path.join(folder, "textfx.py"))
    add("FALTA" if ref else "AVISO", "fonte Impact não encontrada" + (" (este projeto é do estilo da referência: as palavras da letra usam a Impact)" if ref else
        " (só o estilo da referência, com as palavras da letra, precisa dela)"),
        "instale a Impact (vem com o Windows: Configurações > Personalização > Fontes), ou aponte IMPACT_FONT para o .ttf de outra fonte pesada e condensada")


def check_disk(folder):
    try:
        free = shutil.disk_usage(folder).free / 2**30
    except OSError as e:
        add("AVISO", f"não consegui ler o espaço livre de {folder} ({e})")
        return
    drive = os.path.splitdrive(os.path.abspath(folder))[0] or "/"
    txt = f"espaço livre em {drive}: {num(free)} GB (edit de 30 s: {int(MIN_GB)} a {int(NEED_GB)} GB de frames interpolados, mais o master)"
    if free < MIN_GB:
        add("FALTA", txt, "libere espaço ou rode numa pasta de outro disco; os frames interpolados (store/) podem ser apagados depois de entregar")
    elif free < NEED_GB:
        add("AVISO", txt + ": cabe o estilo da casa, o da referência (1080p largo) pode não caber",
            "se faltar, libere espaço ou use outro disco; some também o tamanho das cópias convertidas se os clipes não forem 1080p60")
    else:
        add("OK", txt)


def check_folder(folder):
    low = folder.lower().replace("\\", "/")
    test = os.path.join(folder, f".doctor_{os.getpid()}.tmp")
    try:
        with open(test, "wb") as f:
            f.write(b"x" * 4096)
        os.replace(test, test + ".ok")
        os.remove(test + ".ok")
        d = os.path.join(folder, f".doctor_{os.getpid()}.d")
        os.mkdir(d)
        os.rmdir(d)
        add("OK", f"gravar, renomear e apagar arquivos funciona em {folder}")
    except OSError as e:
        for p in (test, test + ".ok"):
            try:
                os.remove(p)
            except OSError:
                pass
        add("FALTA", f"não consigo gravar em {folder}: {e.strerror or e}",
            "pasta somente leitura ou bloqueada: o 'Acesso controlado a pastas' do Windows Defender bloqueia o Python em Documentos/Imagens/Vídeos/Desktop "
            "(Segurança do Windows > Proteção contra vírus > Acesso controlado a pastas > permita o python.exe do venv, ou use outra pasta, ex.: C:/Editor); "
            "o OneDrive também trava arquivos")
        return
    if "onedrive" in low:
        add("AVISO", "a pasta está dentro do OneDrive: a sincronização trava e duplica os milhares de JPG do store/ (e 'arquivos sob demanda' somem do disco)",
            "use uma pasta fora do OneDrive (ex.: C:/Editor/<nome do video>), ou pause a sincronização durante o trabalho")
    if len(folder) > 120:
        add("AVISO", f"caminho longo ({len(folder)} caracteres): o Windows limita caminhos a 260 e o store/ acrescenta ~25", "use uma pasta mais curta, ex.: C:/Editor")


def check_ascii(folder):
    bad = [c for c in folder if ord(c) > 127]
    if not bad:
        add("OK", "o caminho da pasta só tem caracteres ASCII (sem acento)")
        return
    note = ""
    jpg = ".doctor_acento.jpg"
    try:
        import cv2
        import numpy as np
        try:
            cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
        except AttributeError:
            pass
        ok, buf = cv2.imencode(".jpg", np.zeros((8, 8, 3), np.uint8))
        buf.tofile(jpg)
        rel, ab = cv2.imread(jpg) is not None, cv2.imread(os.path.abspath(jpg)) is not None
        note = "; cv2.imread aqui: caminho relativo (o que os scripts usam) %s, caminho absoluto %s" % ("abre" if rel else "NÃO abre", "abre" if ab else "NÃO abre")
    except Exception:
        pass
    finally:
        try:
            os.remove(jpg)
        except OSError:
            pass
    add("AVISO", f"o caminho tem acentos ({''.join(sorted(set(bad)))}){note}; ffmpeg e RIFE aceitam, mas o OpenCV do Windows falha em caminhos assim e um script que monte "
        "um caminho absoluto pode quebrar",
        "o mais seguro é um projeto numa pasta sem acento nem 'ç' (ex.: C:/Editor/<nome sem acento>); os clipes de origem podem ficar onde estão", "o caminho tem acentos")


def main():
    folder = os.getcwd()
    print(f"Diagnóstico da skill editing-gameplay-montages  |  pasta: {folder}\n", flush=True)
    check_python()
    pk = check_packages()
    check_ffmpeg(folder)
    model = check_model()
    if pk:
        check_rife(model)
    else:
        add("FALTA", "teste do RIFE não feito: pacotes faltando (acima)")
    check_font(folder)
    check_disk(folder)
    check_folder(folder)
    check_ascii(folder)
    falta = [r for r in rows if r[0] == "FALTA"]
    aviso = [r for r in rows if r[0] == "AVISO"]
    print()
    if not falta:
        print("PRONTO" + (f"  ({len(aviso)} aviso{'s' if len(aviso) > 1 else ''}, nada que impeça de começar)" if aviso else ""))
    else:
        print("FALTA: " + "; ".join(r[3] for r in falta))
    seen = set()
    for label, group in (("Como resolver", falta), ("Sobre os avisos", aviso)):
        fixes = {}
        for r in group:
            if r[2] and r[2] not in seen:
                fixes.setdefault(r[2], []).append(r[3])           # o mesmo conserto para vários itens (pacotes) sai uma vez
        if fixes:
            print(f"\n{label}:")
            for i, (fix, shorts) in enumerate(fixes.items(), 1):
                seen.add(fix)
                print(f"  {i}. {'; '.join(shorts)}\n     -> {fix}")
    return 1 if falta else 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == CHILD:
        child_main(sys.argv[2])
    sys.exit(main())
