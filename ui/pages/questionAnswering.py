import pytz
import requests
import operator
from utils import dbManager
import streamlit as st
from utils import spreadManager
from datetime import datetime
from annotated_text import annotated_text

"""
Variables globales:
- timezone: Huso horario cuyas horas vamos a usar en nuestra hoja
- knowledgeBases: Lista de bases de conocimiento para nuestra consulta
- QAService: Url del servicio de Question-Answering
- dbDirection: Direccion de la base de datos
- spreadsheet: Nombre del Libro de Calculo 
- spreadsheet_id: Identificador de nuestro Libro de Calculo
- validationSheet: Nombre de la Hoja a modificar (hoja de validacion)
"""

timezone = pytz.timezone("Europe/Madrid")

knowledgeBases = ["wikidata","dbpedia","cord19"]
QAService = "http://127.0.0.1:5000/muheqa/"
dbDirection = "mongodb://localhost:27017"

spreadsheet = "MuHeQa_Validation"
spreadsheetId = "1TY6Tj1OwITOW3o1nYRFFRY1bunvHNImUj-J0omRq4-I"
validationSheet = "Validation"

def queryJSON(queryURL, question):
    """
    Funcion auxiliar que realiza las preguntas al servidor de EQA
    """
    files = {
        'question': (None, question),
    }
    response = requests.get(queryURL, files = files)
    #Si la respuesta del servidor es distinta de None, devolvemos esta respuesta en formato json.
    if response:
        return response.json()

def main():

    @st.cache(show_spinner=False, allow_output_mutation=True)
    def getAnswers(question):
        """
        Funcion auxiliar que obtiene una lista con todas las respuestas sobre las distintas bases de conocimiento
        """
        answerList = [
        ]

        for i in knowledgeBases:
            queryURL = QAService + i + "/en?evidence=true"
            answer = queryJSON(queryURL,question)
            #Si la respuesta es distinta de None, guardamos la fuente y agregamos la respuesta a la lista de contestaciones
            if answer:
                answer["source"] = i
                answerList.append(answer)

        return answerList
    
    def annotateContext(response, answer, context, answerStart, answerEnd):
        '''
        Funcion auxiliar que anota la respuesta sobre el texto de evidencia
        '''
        tag = "ANSWER"
        color = "#adff2f"
        #Buscamos la respuesta en el texto
        answerInText = (response["evidence"]["summary"])[answerStart:answerEnd]
        #Si la respuesta en el texto es distinta de la respuesta en el json:
        if answer != answerInText:
            #Cambiamos la etiqueta a "EVIDENCE" y el color a a azul
            tag = "EVIDENCE"
            color = "#8ef"
        #Marcamos en el texto de evidencia la respuesta y lo mostramos en la interfaz
        annotated_text(context[:answerStart],(answerInText,tag,color),context[answerEnd:],)

    #Creamos la conexion para la base de datos (datasets) y el Libro de Calculo (validacion)
    spread = spreadManager.SpreadManager(spreadsheet, spreadsheetId, validationSheet)
    db = dbManager.DbManager(dbDirection)

    #Subtitulo de la seccion de pregunta y respuesta
    st.subheader('MuHeQa UI - Question Answering over Multiple and Heterogeneous Knowledge Bases')
    
    #Texto del cuerpo de la pagina web con Markdown (convierte de texto a HTML)
    st.markdown("""
    Write any question below or use a random one from a pre-loaded datasets!
    """, unsafe_allow_html=True)

    #Lista de Hojas de Calculo con Datasets en nuestra base de datos
    selectorList = ["All"] 
    selectorList.extend(db.getCollections())
    
    #Buscador para realizar preguntas
    question = st.text_input("")

    #Selector para el Dataset del que provendran las preguntas aleatorias
    dataset = st.selectbox("Select a DataSet", selectorList)
    #Boton que hace una pregunta aleatoria
    randomQuestion = st.button("Random Question")
    
    #Inicializamos la variable modeLAnswer para que no sea referenciada antes de su asignacion
    modelAnswer = None

    if randomQuestion:
        randomDict = db.getRandomDocument(1,dataset)[0]
        question = randomDict["question"]
        modelAnswer = randomDict["answer"]

    #Establecemos el titulo de la barra lateral
    st.sidebar.subheader('Options')
    #Control deslizante para el numero de respuestas a mostrar
    answerNumber = st.sidebar.slider('How many relevant answers do you want?', 1, 10, 1)
    if question:
        st.write("**Question: **", question)
        if modelAnswer:
            #Mostramos la respuesta modelo
            st.write("**Expected Answer: **", modelAnswer)
            st.write("\n")
            #Reseteamos el valor de la respuesta modelo
            modelAnswer = None
        #Mensaje de carga para las preguntas. Se muestra mientras que estas se obtienen.
        with st.spinner(text=':hourglass: Looking for answers...'):
            counter = 0
            highestScoreAnswer = {}
            results = getAnswers(question)
            results.sort(key = operator.itemgetter('confidence'), reverse = True)
            for idx,response in enumerate(results):
                if counter >= answerNumber:
                    break
                counter += 1
                answer = response['answer']
                if answer and answer != "-":
                    context = "..." + response["evidence"]["summary"] + "..."
                    source = response["source"]
                    confidence = response["confidence"]
                    annotateContext(response, answer, context, response["evidence"]["start"], response["evidence"]["end"])
                    st.write("**Answer: **", answer)
                    st.write('**Relevance:** ', confidence , '**Source:** ' , source)
                    if idx == 0:
                        highestScoreAnswer = {
                            "answer": answer,
                            "confidence": confidence
                        }
        st.write("Please rate if our answer has been helpful to you so we can further improve our system!")
        #Botones para validar la respuesta por parte del usuario en columnas separadas          
        col1, col2 = st.columns([1,1])
        with col1:
            isRight = st.button("👍")
        with col2:
            isWrong = st.button("👎")

        #Si se pulsa el boton de correcto/incorrecto:
        if isRight or isWrong:
            #Insertamos en la Spreadsheet de Google
            spread.insertRow([[question, highestScoreAnswer["answer"], str(highestScoreAnswer["confidence"]), isRight, str(datetime.now(tz=timezone))]])
            #Reseteamos los valores de los botones
            isRight = False
            isWrong = False
            #Mensaje de que el input del usuario ha sido registrado
            st.success("✨ Thanks for your input!")

    #Checkbox. Si tenemos respuesta y la caja es marcada, imprimimos las respuestas JSON obtenidas.
    if question and st.sidebar.checkbox('Show JSON Response', key = 0):
        st.subheader('API JSON Response')
        st.write(results)