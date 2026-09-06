"""`scripts/ci_esperar_host.py`: espera TCP para CI, sin dependencias externas.

No es parte del paquete instalado (vive en `scripts/`, no en `src/`): se carga
por ruta con `importlib`, igual que lo haria cualquier pipeline que lo invoque
como script suelto -no como un modulo de `sibutestlab8583`.
"""

from __future__ import annotations

import importlib.util
import socket
import threading
import time
from pathlib import Path

_RUTA = Path(__file__).resolve().parent.parent / "scripts" / "ci_esperar_host.py"
_SPEC = importlib.util.spec_from_file_location("ci_esperar_host", _RUTA)
assert _SPEC is not None and _SPEC.loader is not None
ci_esperar_host = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ci_esperar_host)


def _puerto_libre() -> int:
    """Un puerto que en este instante nadie escucha -el bind se libera al
    salir del `with`, asi que el numero queda disponible para el resto del
    test, pero nada esta atendiendo ahi todavia."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_esperar_detecta_un_puerto_que_ya_esta_escuchando():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.bind(("127.0.0.1", 0))
        servidor.listen(1)
        puerto = servidor.getsockname()[1]
        assert ci_esperar_host.esperar("127.0.0.1", puerto, timeout=2.0, intervalo=0.05) is True


def test_esperar_agota_el_timeout_si_nadie_escucha():
    puerto = _puerto_libre()
    assert ci_esperar_host.esperar("127.0.0.1", puerto, timeout=0.3, intervalo=0.05) is False


def test_esperar_detecta_el_host_apenas_empieza_a_escuchar():
    """El caso real de CI: `sibu-host-demo` arranca DESPUES de que empieza el
    sondeo -la espera debe sobrevivir esa carrera, no fallar por haber medido
    demasiado pronto."""
    puerto = _puerto_libre()

    def _levantar_con_retraso() -> None:
        time.sleep(0.2)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", puerto))
            s.listen(1)
            time.sleep(1.0)

    hilo = threading.Thread(target=_levantar_con_retraso, daemon=True)
    hilo.start()
    try:
        assert ci_esperar_host.esperar("127.0.0.1", puerto, timeout=2.0, intervalo=0.05) is True
    finally:
        hilo.join(timeout=2.0)


def test_host_y_puerto_y_timeout_son_parametrizables_por_argumentos():
    args = ci_esperar_host._argumentos(
        ["--host", "example.test", "--puerto", "9999", "--timeout", "5", "--intervalo", "0.1"]
    )
    assert args.host == "example.test"
    assert args.puerto == 9999
    assert args.timeout == 5.0
    assert args.intervalo == 0.1


def test_main_devuelve_0_si_el_host_responde():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.bind(("127.0.0.1", 0))
        servidor.listen(1)
        puerto = servidor.getsockname()[1]
        codigo = ci_esperar_host.main(
            ["--host", "127.0.0.1", "--puerto", str(puerto), "--timeout", "2"]
        )
    assert codigo == 0


def test_main_devuelve_distinto_de_cero_y_mensaje_claro_si_no_responde(capsys):
    puerto = _puerto_libre()
    codigo = ci_esperar_host.main(
        ["--host", "127.0.0.1", "--puerto", str(puerto), "--timeout", "0.3", "--intervalo", "0.05"]
    )
    assert codigo != 0
    salida = capsys.readouterr()
    assert "no aceptó conexiones" in salida.err
