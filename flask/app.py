from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
import serial
import time
import serial.tools.list_ports
from werkzeug.utils import secure_filename
import os
import threading

Baudios = 115200
Puerto = 'COM11'

UsuariosConectados = 0b00000000 # Esta variable almacenara en cada bit los usuarios conectados
global Serial, PorcentajeBaterias, Usuario, PuntajeJugador, PuntajePregunta, NumeroPregunta, Posicion, Turno, PuestoFinal

PorcentajeBaterias = [None] * 5 # Crea un vector vacio de 5 posiciones


global integer_value

integer_values = []
last_received_values = []

app = Flask(__name__)

def RecepcionSerial():
    Serial = serial.Serial(Puerto, Baudios) 

    while True:
        if Serial.in_waiting > 0:
            ByteSerial = int.from_bytes(Serial.read(), "big") # Leer primer byte entrante
            print(f"Valor byte: {ByteSerial}")
            if ByteSerial == 0: # Solicitar lista de usuarios conectados
                EnvioSerial(0)
            elif ByteSerial == 1: # Recibe nuevo usuario conectado
                if Serial.in_waiting > 0:
                    Usuario = int.from_bytes(Serial.read(), "big")

            elif ByteSerial == 2: # Recibe nivel de bateria
                if Serial.in_waiting > 1:
                    Usuario = int.from_bytes(Serial.read(), "big")

            elif ByteSerial == 3: # Recibe pulso de boton
                if Serial.in_waiting > 0:
                    Usuario = int.from_bytes(Serial.read(), "big")

            else:
                print('Error en RecepcionSerial')


def EnvioSerial(var1):
            print(f"Enviando con identificador: {var1}")
            if var1 == 0: # Enviar lista de usuarios conectados
                Serial.write(b'\x00' + UsuariosConectados)
            elif var1 == 1: # Enviar puntaje jugadores
                Serial.write(b'\x01' + Usuario + PuntajeJugador)
            elif var1 == 2: # Iniciar nueva pregunta
                Serial.write(b'\x02' + NumeroPregunta + PuntajePregunta)
            elif var1 == 3: # Envio posicion del jugador
                Serial.write(b'\x03' + Usuario + Posicion)
            elif var1 == 4: # Envio turno actual del jugador a responder
                Serial.write(b'\x04' + Turno)
            elif var1 == 5: # Envio a jugador que contesto correctamente
                Serial.write(b'\x05' + Usuario)
            elif var1 == 6: # Envio de puestos finales
                serial.write(b'\x06' + Usuario + PuestoFinal + PuntajeJugador)
            else:
                print('error')



# Conexion base de datos
conn_database = sqlite3.connect('database.db')
cursor_database = conn_database.cursor()


cursor_database.execute('''
    CREATE TABLE Estadisticas_Jugadores(
        id INTEGER PRIMARY KEY,
        NumeroJugador INTEGER,
        Nombre TEXT,
        Puntaje INTEGER,
    )
''')

cursor_database.execute('''
    CREATE TABLE Preguntas_Respuestas(
        NumeroPregunta INTEGER,
        PuntajePregunta INTEGER,
        NumeroRespuestaCorrecta INTEGER,
        Pregunta TEXT,
        PosibleRespuesta1 TEXT,
        PosibleRespuesta2 TEXT,
        PosibleRespuesta3 TEXT,
        PosibleRespuesta4 TEXT,
    )
''')

cursor_database.commit()


def CargarPreguntasRespuestas(Ruta):

    Numero_Pregunta = 0
    Puntaje_Pregunta = 0
    Numero_Respuesta_Correcta = 0
    Pregunta = ""
    Posibles_Respuestas = ["","","",""]
    contador = 0 # Incrementa con cada posible respuesta en la pregunta

    with open(Ruta, 'r') as archivo:
        for linea in archivo:
            if not Pregunta:
                Numero_Pregunta += 1
                Pregunta, Puntaje_Pregunta = linea.strip().split('-') # Divide la línea en la pregunta y el puntaje
                Puntaje_Pregunta = int(Puntaje_Pregunta) # Convierte el puntaje a un entero
                cursor_database.execute(f"ALTER TABLE Estadisticas_Jugadores 
                                        ADD COLUMN Pregunta{Numero_Pregunta} INTEGER")
                conn_database.commit()
            else:
                contador += 1
                if linea.startswith('*'): # Respuesta correcta si la línea comienza con un asterisco
                    Numero_Respuesta_Correcta = contador
                    Posibles_Respuestas[contador - 1] = linea[1:].strip() # Guarda sin asterisco
                else: # De lo contrario es otra posible respuesta
                    Posibles_Respuestas[contador - 1] = linea.strip()
            
            if contador == 4: # Si termino de leer todas las respuestas procede a guardar
                cursor_database.execute('''
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
                ''', (Numero_Pregunta, Puntaje_Pregunta, Numero_Respuesta_Correcta, 
                      Pregunta, Posibles_Respuestas[0], Posibles_Respuestas[1], 
                      Posibles_Respuestas[2], Posibles_Respuestas[3]))

                Puntaje_Pregunta = 0
                Numero_Respuesta_Correcta
                Pregunta = ""
                Posibles_Respuestas = ["","","",""]

    conn_database.commit() # Guarda todos los cambios realizados a la base de datos



def contar_lineas():
    ruta_del_archivo = os.path.join(app.static_folder, 'preguntas.txt')
    with open(ruta_del_archivo, 'r') as f:
        lineas = f.readlines()
        conteo_de_lineas = 0
        for i in range(len(lineas)):
            if i % 5 == 0:
                conteo_de_lineas += 1
        conteo_de_lineas += 70
        return conteo_de_lineas
    
def get_data_from_db():
    with sqlite3.connect('database.db') as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM data")
        datadb = cur.fetchall()
    return datadb


def send_data():
    ser = serial.Serial('COM5', 115200)  # Reemplaza 'COM5' con el puerto correcto
    global integer_values, last_received_values
    while True:
        ser.write(b'\x00')  # Envia un byte en 0
        print("Byte 0 enviado")
        time.sleep(0.5)     # Envia un byte cada 500ms
        if ser.in_waiting > 0:
            incoming_byte = ser.read()  # Lee el byte entrante
            print("Mensaje recibido")
            if incoming_byte == b'\x00':
                print("Byte 0 recibido, deteniendo el envío de bytes")
                break
            
    ser.write(b'\x00') # Identificador
    ser.write(b'\x01') # Usuarios Conectados
    while True:
        if ser.in_waiting > 0:
            incoming_byte = ser.read() # Lee el byte entrante
            integer_value = int.from_bytes(incoming_byte, "big")  # Convierte el byte a entero
            integer_values.append(integer_value)  # Agrega el valor a la lista
            print(f"Byte entrante: {integer_value}")
            
            # Comprueba el primer byte y actúa en consecuencia
            if len(integer_values) == 1:
                if integer_values[0] == 1:
                    expected_bytes = 2
                elif integer_values[0] == 2:
                    expected_bytes = 3
                else:
                    print("Byte desconocido, reiniciando la lista")
                    integer_values = []
                    continue
            
            # Si hemos recibido la cantidad esperada de bytes, guarda los valores y reinicia la lista
            if len(integer_values) == expected_bytes:
                last_received_values = integer_values.copy()  # Guarda los valores antes de reiniciar la lista
                integer_values = []
            

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        dato = request.form.get('dato')
        if dato == 'EMPEZAR':
            threading.Thread(target=send_data, daemon=True).start()  #home
            print("se oprimio empezar")
            return redirect(url_for('pagina2'))
    return render_template('index.html')


@app.route('/Pagina2.html', methods=['GET', 'POST'])
def pagina2():
    if request.method == 'POST':
        data1 = request.form.get('input1')
        data2 = request.form.get('input2')
        data3 = request.form.get('input3')
        data4 = request.form.get('input4')
        with sqlite3.connect('database.db') as conn:
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO data (data1, data2, data3, data4) VALUES (?, ?, ?, ?)
            ''', (data1, data2, data3, data4))
            conn.commit()
        print(data1)
        if 'miArchivo' in request.files:
            archivo = request.files['miArchivo']
            if archivo.filename != '':
                filename = secure_filename('preguntas.txt')
                archivo.save(os.path.join(app.root_path, 'static', filename))
                return redirect(url_for('pagina3'))
        else:
            return render_template('Pagina2.html',data=data)
    return render_template('Pagina2.html')


@app.route('/Pagina3.html', methods=['GET', 'POST'])
def pagina3():
    if request.method == 'POST':
        print("hello world")
    else:
            line=contar_lineas  
            print(line)
            return render_template('Pagina3.html', line=line, data=data, datadb=datadb)
    return render_template('Pagina3.html')


@app.route('/data')
def data():
    global last_received_values
    data = last_received_values
    return jsonify({'data': data})

@app.route('/line')
def line():
    line=contar_lineas()
    return jsonify({'line': line})

@app.route('/datadb')
def datadb():
    datadb=get_data_from_db()
    return jsonify({'datadb': datadb})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)
