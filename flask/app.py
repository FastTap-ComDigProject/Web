import os
import sqlite3
import threading
import time

import serial
import serial.tools.list_ports
from werkzeug.utils import secure_filename

from flask import Flask, jsonify, redirect, render_template, request, url_for

Baudios = 115200
Puerto = "COM7"

global Serial
global PorcentajeBaterias
global Usuario
global UsuariosConectados
global NUsuariosConectados
global PuntajeJugador
global PuntajePregunta
global Presionaron
global Posicion
global Turno
global Podio
global PreguntaActual
global Tiempo_inicio_pregunta
global Tiempo_en_presionar
global Conectado
global UsuarioPosicion

UsuariosConectados = (
    0b00000000  # Esta variable almacenara en cada bit los usuarios conectados
)
PorcentajeBaterias = [None] * 5
Presionaron = [0] * 5
Tiempo_inicio_pregunta = 0
Tiempo_en_presionar = [0] * 5
UsuarioPosicion = [0] * 5
Podio = [None] * 5
Conectado = 0
PreguntaActual = 0
Turno = 0
NUsuariosConectados = 0


global integer_value

integer_values = []
last_received_values = []

app = Flask(__name__)


def IniciarComunicacionSerial():
    global Serial
    try:
        Serial = serial.Serial(Puerto, Baudios)
        print("Comunicación serial iniciada con éxito.")
        time.sleep(2)
        Serial.write(b"\x00")  # Envia un byte en 0
        return 1
    except:
        print("Error com serial.")
        return 0


def RecepcionSerial():
    global Serial
    global UsuariosConectados
    global NUsuariosConectados
    global Presionaron
    global Tiempo_en_presionar
    global Posicion
    global Usuario

    while True:
        if Serial.in_waiting > 0:
            ByteSerial = int.from_bytes(
                Serial.read(), "big"
            )  # Leer primer byte entrante
            print(f"RecepcionSerial, byte entrante: {ByteSerial}")

            if ByteSerial == 0:  # Solicitar lista de usuarios conectados
                EnvioSerial(0)

            elif ByteSerial == 1:  # Recibe nuevo usuario conectado
                if Serial.in_waiting > 0:
                    Usuario = int.from_bytes(Serial.read(), "big")
                    print(f"Recibe nuevo usuario conectado : {Usuario}")
                    UsuariosConectados |= 1 << (
                        Usuario
                    )  # Pone en alto un bit especifico
                    NUsuariosConectados += 1
                    print(f"UsuariosConectados: {NUsuariosConectados}")
                    cursor_database.execute(
                        """INSERT INTO Estadisticas_Jugadores(
                                            NumeroJugador, Puntaje) VALUES (?,?)""",
                        (Usuario, 0),
                    )
                    conn_database.commit()

            elif ByteSerial == 2:  # Recibe nivel de bateria
                if Serial.in_waiting > 1:
                    Usuario = int.from_bytes(Serial.read(), "big")
                    PorcentajeBaterias[Usuario] = int.from_bytes(Serial.read(), "big")

            elif ByteSerial == 3:  # Recibe pulso de boton
                if Serial.in_waiting > 0:
                    Usuario = int.from_bytes(Serial.read(), "big")
                    if Presionaron[Usuario] == 0:
                        Presionaron[Usuario] = 1
                        Posicion += 1
                        Tiempo_en_presionar[Usuario] = (
                            time.time() - Tiempo_inicio_pregunta
                        )
                        EnvioSerial(3)

            else:
                print("Error en RecepcionSerial")


HiloRecepcionSerial = threading.Thread(
    target=RecepcionSerial
)  # Monitorea constantemente la comunicacion serial


def EnvioSerial(var1):
    global Serial
    global UsuariosConectados
    global NUsuariosConectados
    global Tiempo_inicio_pregunta
    global PreguntaActual
    global Turno
    global Posicion
    global UsuarioPosicion
    global Usuario

    print(f"EnvioSerial, identificador: {var1}")
    if var1 == 0:  # Enviar lista de usuarios conectados
        usuarios_conectados_bytes = (UsuariosConectados).to_bytes(1, "big")
        Serial.write(b"\x00" + usuarios_conectados_bytes)

    elif var1 == 1:  # Enviar puntaje jugadores
        for Usuario in range(5):
            cursor_database.execute(
                """SELECT Puntaje FROM Estadisticas_Jugadores 
                                            WHERE NumeroJugador=?""",
                (Usuario,),
            )
            Puntaje = cursor_database.fetchone()
            if Puntaje is not None:
                usuario_bytes = (Usuario).to_bytes(1, "big")
                puntaje_bytes = (int(Puntaje[0] / 50)).to_bytes(1, "big")
                Serial.write(b"\x01" + usuario_bytes + puntaje_bytes)

    elif var1 == 2:  # Iniciar nueva pregunta
        Tiempo_inicio_pregunta = time.time()
        Posicion = 0
        Turno = 0
        for i in range(5):
            Presionaron[i] = 0
            Tiempo_en_presionar[i] = 9999

        cursor_database.execute(
            """SELECT PuntajePregunta FROM Preguntas_Respuestas 
                                        WHERE NumeroPregunta=?""",
            (PreguntaActual,),
        )
        PuntajePregunta = cursor_database.fetchone()
        if PuntajePregunta is not None:
            numero_pregunta_bytes = (PreguntaActual).to_bytes(1, "big")
            puntaje_pregunta_bytes = (int(PuntajePregunta[0] / 50)).to_bytes(1, "big")
            Serial.write(b"\x02" + numero_pregunta_bytes + puntaje_pregunta_bytes)

    elif var1 == 3:  # Envio posicion del jugador
        UsuarioPosicion[Posicion] = Usuario
        usuario_bytes = (Usuario).to_bytes(1, "big")
        posicion_bytes = (Posicion).to_bytes(1, "big")
        print(f"Envio posicion jugador, usuario: {Usuario}")
        Serial.write(b"\x03" + usuario_bytes + posicion_bytes)

    elif var1 == 4:  # Envio turno actual del jugador a responder
        Turno += 1
        if not (Turno > NUsuariosConectados):
            turno_bytes = (Turno).to_bytes(1, "big")
            print(f"Envio turno actual del jugador a responder, Turno: {Turno}")
            Serial.write(b"\x04" + turno_bytes)

    elif var1 == 5:  # Envio a jugador que contesto correctamente
        if not (Turno > NUsuariosConectados):
            cursor_database.execute(
                """SELECT PuntajePregunta FROM Preguntas_Respuestas 
                                            WHERE NumeroPregunta=?""",
                (PreguntaActual,),
            )
            PuntajePregunta = cursor_database.fetchone()
            cursor_database.execute(
                """SELECT Puntaje FROM Estadisticas_Jugadores 
                                            WHERE NumeroJugador=?""",
                (UsuarioPosicion[Turno],),
            )
            PuntajeJugador = cursor_database.fetchone()
            cursor_database.execute(
                f"""UPDATE Estadisticas_Jugadores SET Pregunta{PreguntaActual} = ? 
                                            WHERE NumeroJugador = ?""",
                (PuntajePregunta[0], UsuarioPosicion[Turno]),
            )
            cursor_database.execute(
                """UPDATE Estadisticas_Jugadores SET Puntaje = ? 
                                            WHERE NumeroJugador = ?""",
                (PuntajeJugador[0] + PuntajePregunta[0], UsuarioPosicion[Turno]),
            )
            conn_database.commit()

            print(
                f"Envio a jugador que contesto correctamente, usuario: {UsuarioPosicion[Turno]}"
            )
            usuario_bytes = (UsuarioPosicion[Turno]).to_bytes(1, "big")
            Serial.write(b"\x05" + usuario_bytes)

    elif var1 == 6:  # Envio de puestos finales
        Posicion = 0
        matriz = [None] * 5
        for i in range(5):
            cursor_database.execute(
                """SELECT NumeroJugador, Puntaje FROM
                                    Estadisticas_Jugadores WHERE NumeroJugador=?""",
                (i,),
            )
            fetch_result = cursor_database.fetchone()
            if fetch_result is not None:
                matriz[i] = fetch_result
        matriz = sorted(
            matriz, key=lambda x: x[1] if x is not None else float("-inf"), reverse=True
        )

        for i in range(5):
            if matriz[i] is not None:
                usuario_bytes = (matriz[i][0]).to_bytes(1, "big")
                posicion_final_bytes = (i + 1).to_bytes(1, "big")
                puntaje_bytes = (int(matriz[i][1] / 50)).to_bytes(1, "big")

                # Enviamos los datos
                Serial.write(
                    b"\x06" + usuario_bytes + posicion_final_bytes + puntaje_bytes
                )

    else:
        print("Error EnvioSerial")


# Conexion base de datos
conn_database = sqlite3.connect("database.db", check_same_thread=False)
cursor_database = conn_database.cursor()
cursor_EstadisticasJugadores = conn_database.cursor()

# Eliminar la tabla Estadisticas_Jugadores
cursor_database.execute("DROP TABLE IF EXISTS Estadisticas_Jugadores")

# Eliminar la tabla Preguntas_Respuestas
cursor_database.execute("DROP TABLE IF EXISTS Preguntas_Respuestas")

conn_database.commit()

cursor_database.execute(
    """
    CREATE TABLE Estadisticas_Jugadores(
        NumeroJugador INTEGER,
        Nombre TEXT,
        Puntaje INTEGER
    )
"""
)

cursor_database.execute(
    """
    CREATE TABLE Preguntas_Respuestas(
        NumeroPregunta INTEGER,
        PuntajePregunta INTEGER,
        NumeroRespuestaCorrecta INTEGER,
        Pregunta TEXT,
        PosibleRespuesta1 TEXT,
        PosibleRespuesta2 TEXT,
        PosibleRespuesta3 TEXT,
        PosibleRespuesta4 TEXT
    )
"""
)

conn_database.commit()


def CargarPreguntasRespuestas(dottxt):  #

    Numero_Pregunta = 0
    Puntaje_Pregunta = 0
    Numero_Respuesta_Correcta = 0
    Pregunta = ""
    Posibles_Respuestas = ["", "", "", ""]
    contador = 0  # Incrementa con cada posible respuesta en la pregunta

    lineas = dottxt.read().decode("utf-8").splitlines()

    print(lineas)
    for linea in lineas:
        if not Pregunta:
            Numero_Pregunta += 1
            if "-" in linea:
                Pregunta, Puntaje_Pregunta = linea.strip().split("-")
            else:
                print(
                    f"La línea '{linea}' no contiene un '-'"
                )  # Divide la línea en la pregunta y el puntaje
            Puntaje_Pregunta = int(Puntaje_Pregunta)  # Convierte el puntaje a un entero
            cursor_database.execute(
                f"ALTER TABLE Estadisticas_Jugadores ADD COLUMN Pregunta{Numero_Pregunta} INTEGER"
            )
            conn_database.commit()
        else:
            contador += 1
            if linea.startswith(
                "*"
            ):  # Respuesta correcta si la línea comienza con un asterisco
                Numero_Respuesta_Correcta = contador
                Posibles_Respuestas[contador - 1] = linea[
                    1:
                ].strip()  # Guarda sin asterisco
            else:  # De lo contrario es otra posible respuesta
                Posibles_Respuestas[contador - 1] = linea.strip()

        if contador == 4:  # Si termino de leer todas las respuestas procede a guardar
            cursor_database.execute(
                """
                INSERT INTO Preguntas_Respuestas(
                    NumeroPregunta,
                    PuntajePregunta,
                    NumeroRespuestaCorrecta,
                    Pregunta,
                    PosibleRespuesta1,
                    PosibleRespuesta2,
                    PosibleRespuesta3,
                    PosibleRespuesta4
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    Numero_Pregunta,
                    Puntaje_Pregunta,
                    Numero_Respuesta_Correcta,
                    Pregunta,
                    Posibles_Respuestas[0],
                    Posibles_Respuestas[1],
                    Posibles_Respuestas[2],
                    Posibles_Respuestas[3],
                ),
            )

            contador = 0
            Puntaje_Pregunta = 0
            Numero_Respuesta_Correcta
            Pregunta = ""
            Posibles_Respuestas = ["", "", "", ""]

    conn_database.commit()  # Guarda todos los cambios realizados a la base de datos


def QuitarPuntos(var1):
    cursor_database.execute(
        """SELECT Puntaje FROM Estadisticas_Jugadores 
                                            WHERE NumeroJugador=?""",
        (UsuarioPosicion[Turno],),
    )
    PuntajeJugador = cursor_database.fetchone()
    NuevoPuntaje = max(0, PuntajeJugador[0] - var1)
    cursor_database.execute(
        f"""UPDATE Estadisticas_Jugadores SET Pregunta{PreguntaActual} = ? 
                                            WHERE NumeroJugador = ?""",
        (PuntajeJugador[0] - NuevoPuntaje, UsuarioPosicion[Turno]),
    )
    cursor_database.execute(
        """UPDATE Estadisticas_Jugadores SET Puntaje = ? 
                                            WHERE NumeroJugador = ?""",
        (NuevoPuntaje, UsuarioPosicion[Turno]),
    )
    conn_database.commit()


def ConsultarJugadoresConectados():
    global UsuariosConectados
    vector = [None] * 5
    for i in range(5):
        vector[i] = (UsuariosConectados >> i) & 1
    return vector


def ConsultarPreguntasRespuestas():
    global PreguntaActual
    cursor_database.execute(
        "SELECT * FROM Preguntas_Respuestas WHERE NumeroPregunta=?", (PreguntaActual,)
    )
    var2 = cursor_database.fetchone()
    if var2 is not None:
        print(f"ConsultarPreguntasRespuestas: {str(var2)}")
        return str(var2)
    else:  # Cuando no hay otra pregunta disponible
        print(f"No hay mas preguntas: {str(var2)}")
        return None


def ConsultarEstadisticasJugadores():
    global Presionaron
    global Tiempo_en_presionar

    matriz = [None] * 5
    for i in range(5):
        cursor_EstadisticasJugadores.execute(
            """SELECT NumeroJugador, Nombre, Puntaje FROM
                                Estadisticas_Jugadores WHERE NumeroJugador=?""",
            (i,),
        )
        fetch_result = cursor_EstadisticasJugadores.fetchone()
        if fetch_result is not None:
            matriz[i] = fetch_result + tuple(
                [
                    Presionaron[i],
                    Tiempo_en_presionar[i],
                ]
            )
    return sorted(
        [x for x in matriz if x is not None], key=lambda x: x[4]
    )  # Ordena la matriz segun el tiempo en presionar y devuelve


def ConsultarPodio():
    matriz = [None] * 5
    for i in range(5):
        cursor_database.execute(
            """SELECT NumeroJugador, Nombre, Puntaje FROM
                                Estadisticas_Jugadores WHERE NumeroJugador=?""",
            (i,),
        )
        fetch_result = cursor_database.fetchone()
        if fetch_result is not None:
            matriz[i] = fetch_result
    return sorted(
        matriz, key=lambda x: x[2] if x is not None else float("-inf"), reverse=True
    )


# Ordena la matriz segun el puntaje mayor y devuelve


######################### Funciones para la pagina de Index
@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        dato = request.form.get("dato")
        if dato == "EMPEZAR":
            HiloRecepcionSerial.start()
            return redirect(url_for("PaginaConexionUsuarios"))
    return render_template("index.html", IniciarComSer=IniciarComSer)


@app.route("/IniciarComSer")
def IniciarComSer():
    global Conectado
    if Conectado == 0:
        Conectado = IniciarComunicacionSerial()
    return jsonify({"Conectado": Conectado})


######################### Funciones para la pagina de ConexionUsuarios
@app.route("/ConexionUsuarios.html", methods=["GET", "POST"])
def PaginaConexionUsuarios():
    if request.method == "POST":
        nombre = [None] * 5
        nombre[0] = request.form.get("input1")
        nombre[1] = request.form.get("input2")
        nombre[2] = request.form.get("input3")
        nombre[3] = request.form.get("input4")
        for Usuario in range(5):
            cursor_database.execute(
                """SELECT NumeroJugador FROM Estadisticas_Jugadores 
                                    WHERE NumeroJugador=?""",
                (Usuario,),
            )
            if cursor_database.fetchone() is not None:
                cursor_database.execute(
                    """UPDATE Estadisticas_Jugadores SET Nombre = ? 
                                        WHERE NumeroJugador = ?""",
                    (nombre[Usuario], Usuario),
                )
        conn_database.commit()
        archivo = request.files["miArchivo"]
        if archivo.filename != "":
            CargarPreguntasRespuestas(archivo)

        return "/Juego.html"  # Pagina a donde redirigir

    return render_template("ConexionUsuarios.html", VectConUsu=VectConUsu)


@app.route("/VectConUsu")
def VectConUsu():
    return jsonify({"JugadoresConectados": ConsultarJugadoresConectados()})


######################### Funciones para la pagina de Juego
@app.route("/Juego.html", methods=["GET", "POST"])
def PaginaJuego():
    return render_template("Juego.html", EstJugadores=EstJugadores)


@app.route("/ControlPregunta", methods=["GET", "POST"])
def ControlPregunta():
    global PreguntaActual
    if request.method == "POST":
        id = request.form.get("id")
        if id == "SIGUIENTE":
            PreguntaActual += 1
            Consulta = ConsultarPreguntasRespuestas()
            if Consulta == None:  # Cuando se acaban las preguntas
                EnvioSerial(6)  # Envio de puestos finales
                print("podio")
                return "SinPreguntas"
            EnvioSerial(2)  # Iniciar nueva pregunta
            EnvioSerial(1)  # Enviar puntaje jugadores
            EnvioSerial(4)  # Envio turno actual del jugador a responder
            return Consulta
        if id == "BIEN":
            EnvioSerial(5)  # Envio a jugador que contesto correctamente
        if id == "MAL":
            QuitarPuntos(50)  # Cuando responde mal se le penaliza
            EnvioSerial(4)  # Envio turno actual del jugador a responder
    return "Solicitud no válida", 400


@app.route("/EstJugadores")
def EstJugadores():
    return jsonify({"EstJugadores": ConsultarEstadisticasJugadores()})


######################### Funciones para la pagina de Podio
@app.route("/Podio.html", methods=["GET", "POST"])
def Podio():
    data = ConsultarPodio()
    return render_template("Podio.html", data=data)


@app.route("/Podio")
def PodioData():
    data = ConsultarPodio()
    return jsonify({"data": data})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=True)
