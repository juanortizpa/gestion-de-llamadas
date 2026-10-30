"""Casos dorados SINTETICOS (sin datos personales) para medir el sistema. Se arman con tests/synthetic/builder.py.

Lo esperado de cada caso se decide por construccion (que se le quito o se le cambio a la llamada buena), NUNCA mirando lo
que responde el sistema. Los casos son 100 % inventados: no cuentan como validacion contra el golden set real (D-19).

  AUDIT_CASES   llamadas con un fallo conocido -> que criterios deben salir 1/0 y como debe terminar la llamada
  RAG_CORPUS    llamadas con temas distintos para probar la busqueda del Asistente
  RAG_QUESTIONS preguntas con la llamada (y la frase) donde esta la respuesta
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "synthetic"))
from builder import A, C, GOOD, build, variant  # noqa: E402

CODES = ["P1", "P2", "V1", "V2", "G1", "G2", "C1", "C2", "Z1", "Z2"]


@dataclass
class Caso:
    id: str
    desc: str
    turns: list
    falla: dict = field(default_factory=dict)       # criterios que DEBEN salir 0 (el resto debe salir 1)
    cierre: str = "finalizada"                      # finalizada | cortada | incompleta
    sub: dict = field(default_factory=dict)         # "C1.comprende_la_necesidad": True/False si difiere del criterio
    duration: float | None = None
    low_prob: tuple = ()                            # indices de turnos con transcripcion de baja confianza (avg_prob 0.5)

    @property
    def esperado(self) -> dict:
        return {c: 0 if c in self.falla else 1 for c in CODES}

    def transcript(self) -> dict:
        tr = build(self.turns, duration=self.duration)
        tr["call"]["call_id"] = self.id
        for i in self.low_prob:
            tr["turns"][i]["avg_prob"] = 0.5
        return tr


def _insert(base, at, extra):
    return list(base[:at]) + list(extra) + list(base[at:])


_REPITE = [(A, "Perdón, ¿qué es lo que necesitaba?", 1), (C, "Le repito, una ecografía abdominal.", 1),
           (A, "¿Me repite qué examen era?", 1), (C, "Ecografía abdominal, ya se lo dije dos veces.", 1)]

AUDIT_CASES: list[Caso] = [
    Caso("A01_completa", "Llamada buena: cumple los 10 criterios y termina con despedida", GOOD),
    Caso("A02_sin_saludo", "El asesor no saluda, no dice la entidad ni su nombre",
         variant(GOOD, replace={0: "Dígame, ¿qué necesita?"}), falla={"P1": 0}),
    Caso("A03_sin_algo_mas", "Se despide sin preguntar si necesita algo más",
         variant(GOOD, replace={10: "Listo, hasta luego."}), falla={"Z2": 0}),
    Caso("A04_hold_largo", "Deja al cliente 90 s en espera tras pedirle un momento",
         variant(GOOD, gap={7: 90}), falla={"G1": 0}),
    Caso("A05_sin_documento", "Nunca pide ni confirma el documento",
         variant(GOOD, drop=[2, 3]), falla={"V1": 0}),
    Caso("A06_sin_nombre", "Nunca llama al cliente por su nombre",
         variant(GOOD, replace={4: "Gracias. ¿Tiene la orden médica?"}), falla={"P2": 0}),
    Caso("A07_v2_parafraseado", "Verifica el requisito con otras palabras (el papel del doctor): la IA debe encontrarlo",
         variant(GOOD, replace={4: "Gracias, señora Marta Pérez. ¿Ya tiene en la mano el papel que le dio el doctor para este estudio?"})),
    Caso("A08_v2_nunca_pregunta", "Nunca verifica examen, orden ni requisitos previos",
         variant(GOOD, replace={4: "Gracias, señora Marta Pérez.",
                                8: "Debe presentarse 20 minutos antes de la hora de la cita."}, drop=[5]),
         falla={"V2": 0}),
    Caso("A09_cliente_repite", "El asesor no entiende y el cliente debe repetir la solicitud",
         _insert(GOOD, 2, _REPITE), falla={"C1": 0}),
    Caso("A10_cierre_cliente", "Termina bien, pero sin la despedida típica del asesor: cierra el cliente",
         _insert(variant(GOOD, replace={10: "Con gusto, quedo atenta si necesita algo más."}), 11, [(C, "Listo, muchas gracias, que esté bien.", 1)])),
    Caso("A11_entidad_mal_transcrita", "El STT deforma la entidad (baja confianza): la IA debe aceptar la variante fonética",
         variant(GOOD, replace={0: "Anjiografía de oxidente, buenos días, habla Laura Gómez, ¿en qué le puedo servir?"}), low_prob=(0,)),
    Caso("A12_sin_entidad_dudosa", "No dice la entidad y el STT tiene baja confianza: la IA no debe inventar una cita",
         variant(GOOD, replace={0: "Buenos días, habla Laura Gómez, ¿en qué le puedo servir?"}), falla={"P1": 0}, low_prob=(0,),
         sub={"P1.entidad": False}),
    Caso("A13_cortada", "La llamada se corta a media frase, sin despedida",
         list(GOOD[:7]) + [(A, "Le queda agendada la cita para el lunes 12 de octubre a las 8 de la mañana en la sede de la calle 5 con", 20)],
         cierre="cortada"),
    Caso("A14_incompleta", "Solo se oye al asesor: el cliente nunca habla",
         [(A, "Angiografía de Occidente, buenos días, habla Laura Gómez, ¿en qué le puedo servir?", 0), (A, "¿Aló? ¿Me escucha?", 5),
          (A, "Señor, no lo escucho, voy a cerrar la llamada.", 3), (A, "Hasta luego.", 1)], cierre="incompleta"),
]


# --------------------------------------------------------------------------- RAG
@dataclass
class RagCall:
    id: str
    day: str
    agent: str
    turns: list


def _c(*pairs) -> list:
    """[(A|C, texto), ...] -> turnos (rol, texto, pausa previa de 1 s), el formato de builder.build."""
    return [(s, t, 1) for s, t in pairs]


RAG_CORPUS: list[RagCall] = [
    RagCall("R01", "20261001", "Laura Gómez", _c(
        (A, "Angiografía de Occidente, buenos días, habla Laura Gómez, ¿en qué le puedo servir?"),
        (C, "Buenos días, necesito una resonancia magnética de rodilla, pero soy claustrofóbica y me da pánico estar encerrada en el aparato."),
        (A, "Entiendo, señora. Podemos programarle la resonancia en el equipo abierto de la sede Versalles, que es más amplio."),
        (C, "Ay qué bueno, eso me tranquiliza. ¿Tiene cupo esta semana?"),
        (A, "Sí, el jueves a las 3 de la tarde. Venga con la orden médica y la autorización de la EPS."),
        (C, "Perfecto, muchas gracias."), (A, "Con gusto. ¿Necesita algo más? Hasta luego."))),
    RagCall("R02", "20261001", "Pedro Ruiz", _c(
        (A, "Angiografía de Occidente, buenos días, habla Pedro Ruiz, ¿en qué le puedo servir?"),
        (C, "Hola, quiero cancelar mi cita del viernes porque se me cruzó con una reunión de trabajo que no puedo mover."),
        (A, "Claro que sí. ¿Prefiere que la dejemos cancelada o la reprogramamos para la próxima semana?"),
        (C, "Mejor reprográmela para el martes en la mañana, por favor."),
        (A, "Listo, queda reprogramada para el martes a las 9 de la mañana. Gracias por avisar con tiempo."),
        (C, "Gracias a usted."), (A, "Que tenga un buen día, hasta luego."))),
    RagCall("R03", "20261002", "Laura Gómez", _c(
        (A, "Angiografía de Occidente, buenas tardes, habla Laura Gómez, ¿en qué le puedo servir?"),
        (C, "Quería saber hasta qué hora atienden en la sede norte y si abren los domingos."),
        (A, "La sede norte atiende de lunes a viernes de 6 de la mañana a 6 de la tarde y los sábados hasta el mediodía. Los domingos permanece cerrada."),
        (C, "¿Y hay parqueadero para los pacientes?"),
        (A, "Sí, el parqueadero es gratuito durante la primera hora presentando el comprobante de la cita."),
        (C, "Muy amable, eso era todo."), (A, "Con gusto, hasta luego."))),
    RagCall("R04", "20261002", "Pedro Ruiz", _c(
        (A, "Angiografía de Occidente, buenas tardes, habla Pedro Ruiz, ¿en qué le puedo servir?"),
        (C, "Estoy muy molesto, llevo dos horas esperando en la sede y nadie me atiende, tenía cita a las 2."),
        (A, "Lamento mucho la demora, señor. Voy a escalar su caso con el coordinador de la sede para que lo atiendan de inmediato."),
        (C, "Es una falta de respeto con uno, quiero poner una queja formal."),
        (A, "Entiendo su inconformidad. Le registro la queja ahora mismo y recibirá respuesta en los próximos ocho días."),
        (C, "Está bien, gracias."), (A, "Disculpe de nuevo las molestias. Hasta luego."))),
    RagCall("R05", "20261003", "Laura Gómez", _c(
        (A, "Angiografía de Occidente, buenos días, habla Laura Gómez, ¿en qué le puedo servir?"),
        (C, "Necesito agendar una mamografía, pero mi autorización de Nueva EPS todavía no ha salido."),
        (A, "Para agendar necesitamos la autorización aprobada. Usted debe tramitarla por la línea de la EPS y luego nos llama de nuevo."),
        (C, "¿Y cuánto se demoran en aprobarla normalmente?"),
        (A, "Suele tardar entre tres y cinco días hábiles, pero eso lo define la EPS."),
        (C, "Entiendo, la llamo cuando la tenga."), (A, "Perfecto. ¿Algo más? Hasta luego."))),
    RagCall("R06", "20261003", "Pedro Ruiz", _c(
        (A, "Angiografía de Occidente, buenos días, habla Pedro Ruiz, ¿en qué le puedo servir?"),
        (C, "Me ordenaron una tomografía con medio de contraste, ¿qué preparación debo hacer?"),
        (A, "Debe ir en ayuno de seis horas y traer un examen de creatinina reciente, de máximo tres meses."),
        (C, "¿Puedo tomar mis pastillas de la tensión por la mañana?"),
        (A, "Sí, con un sorbo de agua. Lo demás en ayuno."),
        (C, "Gracias, entendido."), (A, "Con gusto. ¿Necesita algo más? Hasta luego."))),
    RagCall("R07", "20261004", "Laura Gómez", _c(
        (A, "Angiografía de Occidente, buenas tardes, habla Laura Gómez, ¿en qué le puedo servir?"),
        (C, "Quiero confirmar mi cita de ecografía obstétrica para mañana, estoy embarazada de veinte semanas."),
        (A, "Confirmada para mañana a las 10. Para ese examen debe llegar con la vejiga llena: tome un litro de agua una hora antes y no orine."),
        (C, "Ah, qué bueno que me avisa, no lo sabía."),
        (A, "Recuerde traer la orden y su carné de control prenatal."),
        (C, "Listo, gracias."), (A, "Con gusto, que tenga buena tarde. Hasta luego."))),
    RagCall("R08", "20261004", "Pedro Ruiz", _c(
        (A, "Angiografía de Occidente, buenos días, habla Pedro Ruiz, ¿en qué le puedo servir?"),
        (C, "No tengo EPS, quiero saber cuánto cuesta una angiografía como particular."),
        (A, "Como particular la angiografía coronaria tiene un valor de un millón doscientos mil pesos. Se paga antes del examen."),
        (C, "¿Reciben tarjeta de crédito o toca en efectivo?"),
        (A, "Recibimos tarjeta crédito y débito, y también transferencia."),
        (C, "Gracias, lo pienso y la llamo."), (A, "Con gusto. Hasta luego."))),
    RagCall("R09", "20261005", "Laura Gómez", _c(
        (A, "Angiografía de Occidente, buenos días, habla Laura Gómez, ¿en qué le puedo servir?"),
        (C, "Quiero que me envíen los resultados al correo electrónico y no a la dirección de mi casa, porque me mudé."),
        (A, "Con gusto actualizo el medio de entrega. ¿Me confirma el correo al que desea recibirlos?"),
        (C, "Es maria punto ruiz arroba ejemplo punto com."),
        (A, "Anotado. Desde hoy sus resultados llegarán a ese correo electrónico."),
        (C, "Perfecto, gracias."), (A, "Que tenga buen día, hasta luego."))),
    RagCall("R10", "20261005", "Pedro Ruiz", _c(
        (A, "Angiografía de Occidente, buenas tardes, habla Pedro Ruiz, ¿en qué le puedo servir?"),
        (C, "Tengo cita de radiografía de tórax para mi hija de ocho años, ¿puedo entrar con ella al examen?"),
        (A, "Sí, la mamá o el papá puede acompañar a la niña dentro de la sala; le entregarán un delantal de plomo para protegerla."),
        (C, "¿Y ella necesita algo de preparación?"),
        (A, "No necesita ayuno. Solo recuerde traer el documento de la menor y la orden médica."),
        (C, "Muchas gracias."), (A, "Con gusto, hasta luego."))),
    RagCall("R11", "20261006", "Laura Gómez", _c(
        (A, "Angiografía de Occidente, buenos días, habla Laura Gómez, ¿en qué le puedo servir?"),
        (C, "Me hice un ecocardiograma la semana pasada y todavía no me dan los resultados, ¿cuándo los entregan?"),
        (A, "Los resultados del ecocardiograma se entregan en tres días hábiles después del examen y se pueden recoger en la sede o descargar en línea."),
        (C, "Entonces ya deberían estar listos, ¿verdad?"),
        (A, "Voy a revisar el sistema. Sí, ya están disponibles, se los puedo enviar por correo."),
        (C, "Por favor, gracias."), (A, "Hecho. ¿Necesita algo más? Hasta luego."))),
    RagCall("R12", "20261006", "Pedro Ruiz", _c(
        (A, "Angiografía de Occidente, buenas tardes, habla Pedro Ruiz, ¿en qué le puedo servir?"),
        (C, "Mi papá es adulto mayor y se moviliza en silla de ruedas, ¿pueden ayudarnos a entrar a la sede?"),
        (A, "Claro que sí. Dejo registrada la solicitud de asistencia: una auxiliar lo recibirá en la entrada con la silla y podrá pasar con un acompañante."),
        (C, "Se lo agradezco mucho."),
        (A, "Solo avísenle a la recepcionista cuando lleguen."),
        (C, "Listo."), (A, "Con gusto, hasta luego."))),
    RagCall("R13", "20261007", "Laura Gómez", _c(
        (A, "Angiografía de Occidente, buenos días, habla Laura Gómez, ¿en qué le puedo servir?"),
        (C, "Necesito reagendar mi examen porque tengo una incapacidad médica, estoy con una gripa muy fuerte y fiebre."),
        (A, "Lamento que esté enferma. Le asigno una nueva fecha para dentro de ocho días, ¿le sirve?"),
        (C, "Sí, el próximo miércoles está bien."),
        (A, "Reagendada para el miércoles a las 11. Que se mejore pronto."),
        (C, "Gracias."), (A, "Hasta luego."))),
    RagCall("R14", "20261007", "Pedro Ruiz", _c(
        (A, "Angiografía de Occidente, buenas tardes, habla Pedro Ruiz, ¿en qué le puedo servir?"),
        (C, "Me cobraron dos veces el copago de mi ecografía y quiero que me devuelvan el dinero."),
        (A, "Lamento el inconveniente. Verifico el cobro duplicado y radico la solicitud de devolución con el área de facturación."),
        (C, "¿En cuánto tiempo me devuelven la plata?"),
        (A, "La devolución se acredita en un plazo de diez días hábiles a la misma tarjeta con la que pagó."),
        (C, "Está bien, gracias."), (A, "Con gusto. ¿Algo más? Hasta luego."))),
]


@dataclass
class Pregunta:
    q: str
    call: str               # llamada donde esta la respuesta
    evidencia: str          # frase (sin tildes, minusculas) que debe estar en el fragmento recuperado
    tipo: str               # directa (comparte palabras con el texto) | parafraseada (casi sin palabras en comun)


RAG_QUESTIONS: list[Pregunta] = [
    Pregunta("¿Qué clienta tiene claustrofobia y necesita resonancia?", "R01", "claustrofobica", "directa"),
    Pregunta("¿Quién quería cancelar su cita por una reunión de trabajo?", "R02", "reunion de trabajo", "directa"),
    Pregunta("¿A qué hora atiende la sede norte y abre los domingos?", "R03", "sede norte", "directa"),
    Pregunta("¿Qué cliente puso una queja por esperar dos horas?", "R04", "dos horas", "directa"),
    Pregunta("¿Qué pasa si la autorización de Nueva EPS no ha salido para la mamografía?", "R05", "mamografia", "directa"),
    Pregunta("¿Qué preparación se le da al paciente para tomografía con contraste?", "R06", "creatinina", "directa"),
    Pregunta("¿Qué se le dice a la embarazada sobre la vejiga llena?", "R07", "vejiga llena", "directa"),
    Pregunta("¿Cuánto cuesta la angiografía para un particular?", "R08", "un millon doscientos mil", "directa"),
    Pregunta("¿Quién pidió recibir los resultados por correo electrónico?", "R09", "correo electronico", "directa"),
    Pregunta("¿Puede la mamá entrar con su hija a la radiografía de tórax?", "R10", "delantal de plomo", "directa"),
    Pregunta("¿En cuántos días entregan el ecocardiograma?", "R11", "ecocardiograma", "directa"),
    Pregunta("¿Qué se hizo con el paciente que necesita silla de ruedas?", "R12", "silla de ruedas", "directa"),
    Pregunta("¿Qué clienta tiene miedo a los lugares cerrados durante el estudio de la rodilla?", "R01", "claustrofobica", "parafraseada"),
    Pregunta("¿Quién estaba enojado porque nadie lo atendía a la hora de su turno?", "R04", "dos horas", "parafraseada"),
    Pregunta("¿Qué le dijeron al paciente que no puede comer antes del examen con yodo?", "R06", "ayuno de seis horas", "parafraseada"),
    Pregunta("¿Quién fue cobrado de más y pide su plata de vuelta?", "R14", "copago", "parafraseada"),
    Pregunta("¿Qué paciente cambió su cita porque estaba enfermo?", "R13", "incapacidad", "parafraseada"),
    Pregunta("¿A quién se le explicó cuánto tardan en entregar los exámenes del corazón?", "R11", "ecocardiograma", "parafraseada"),
    Pregunta("¿Qué le dijeron al cliente sin seguro médico sobre las formas de pago?", "R08", "tarjeta", "parafraseada"),
    Pregunta("¿Qué se le dijo a quien preguntó por estacionamiento?", "R03", "parqueadero", "parafraseada"),
]
