# rules.py - Mensajes personalizados por plaga/enfermedad y severidad
# Objetivo: mostrar textos realistas y variados en "¿Por qué aparece?" y "Recomendaciones"

EXPLANATION = {
    # ======== HONGO ========
    "hongo": {
        "why": (
            "Los hongos foliares aparecen por exceso de humedad ambiental, "
            "riego nocturno o falta de ventilación entre plantas. "
            "Las hojas mojadas durante horas favorecen el desarrollo de esporas."
        ),
        "critico": (
            "• Aplicar fungicida sistémico de amplio espectro (ej. azoxistrobina + difenoconazol) rotando FRAC.\n"
            "• Eliminar hojas infectadas y evitar riegos por aspersión.\n"
            "• Mantener ventilación y monitoreo diario hasta reducir el avance."
        ),
        "leve": (
            "• Aplicar fungicida preventivo (mancozeb, cobre o biológicos) en dosis recomendadas.\n"
            "• Favorecer ventilación y espaciamiento entre plantas.\n"
            "• Evitar mojar el follaje durante el riego."
        ),
        "sano": (
            "• Mantener vigilancia visual semanal y asegurar drenaje correcto del terreno.\n"
            "• Evitar riegos excesivos y garantizar ventilación adecuada."
        ),
    },

    # ======== PHYTOPHTHORA (Tizón Tardío) ========
    "phytophthora": {
        "why": (
            "El tizón tardío se produce por la presencia de Phytophthora infestans, "
            "favorecida por temperaturas frescas, lluvias y hojas mojadas por más de 8 horas."
        ),
        "critico": (
            "• Aplicar fungicidas anti-oomicetos (metalaxil-M + mancozeb o cimoxanilo) alternando FRAC.\n"
            "• Cortar hojas muy afectadas y evitar riegos nocturnos.\n"
            "• Monitorear cada 24–48 horas y documentar los avances."
        ),
        "leve": (
            "• Mejorar ventilación del cultivo y espaciar riegos.\n"
            "• Aplicar tratamiento preventivo con fungicida de contacto (mancozeb o clorotalonil).\n"
            "• Vigilar aparición de nuevas lesiones."
        ),
        "sano": (
            "• Mantener rotación de cultivos y monitoreo preventivo.\n"
            "• Evitar acumulación de humedad en hojas y suelo."
        ),
    },

    # ======== GORGOJO ========
    "gorgojo": {
        "why": (
            "El gorgojo andino ataca tubérculos y hojas jóvenes. "
            "Su proliferación ocurre cuando los residuos de cosecha quedan en el campo "
            "y los suelos permanecen agrietados o secos en exceso."
        ),
        "critico": (
            "• Aplicar insecticida de suelo (p.ej. cipermetrina granular o clorpirifos) según etiqueta.\n"
            "• Tapar grietas del suelo y eliminar residuos postcosecha.\n"
            "• Implementar rotación de cultivos no hospedantes."
        ),
        "leve": (
            "• Realizar control biológico (hongos entomopatógenos como Beauveria bassiana).\n"
            "• Eliminar hojas y residuos dañados.\n"
            "• Revisar trampas y mejorar limpieza del área."
        ),
        "sano": (
            "• Mantener higiene del lote y rotación anual de cultivos.\n"
            "• Usar trampas de feromonas como control preventivo."
        ),
    },

    # ======== MINADORES ========
    "minadores": {
        "why": (
            "El minador de la hoja prolifera con clima templado y follaje denso. "
            "Las larvas excavan galerías en el interior de las hojas, reduciendo la fotosíntesis."
        ),
        "critico": (
            "• Aplicar insecticida sistémico (abamectina o spinosad) en rotación de ingredientes activos.\n"
            "• Remover hojas infestadas y malezas hospederas.\n"
            "• Controlar aparición de larvas con monitoreo cada 3 días."
        ),
        "leve": (
            "• Control biológico con parasitoides (Diglyphus isaea, Opius sp.) donde sea posible.\n"
            "• Evitar exceso de nitrógeno y densidad alta de plantas.\n"
            "• Riego controlado para reducir estrés vegetal."
        ),
        "sano": (
            "• Mantener monitoreo regular y eliminar hojas viejas o dañadas.\n"
            "• Promover fauna benéfica natural para control preventivo."
        ),
    },

    # ======== BACTERIAS ========
    "bacterias": {
        "why": (
            "Las bacteriosis se diseminan con salpicaduras de lluvia, heridas en hojas y herramientas sin desinfección. "
            "La alta humedad y temperatura elevan el riesgo de infección."
        ),
        "critico": (
            "• Aplicar compuestos cúpricos o bactericidas biológicos según etiqueta.\n"
            "• Eliminar plantas afectadas y desinfectar utensilios.\n"
            "• Evitar labores con follaje mojado."
        ),
        "leve": (
            "• Uso de extractos vegetales o productos biocontroladores (Bacillus subtilis).\n"
            "• Mejorar drenaje y espaciamiento.\n"
            "• Reducir salpicaduras durante el riego."
        ),
        "sano": (
            "• Monitoreo visual preventivo y desinfección de herramientas.\n"
            "• Rotación de cultivos para reducir patógenos del suelo."
        ),
    },

    # ======== NEMATODO ========
    "nematodo": {
        "why": (
            "Los nematodos prosperan en suelos compactados, con humedad constante y poca rotación de cultivos. "
            "Causan deformaciones en raíces y disminución del vigor vegetal."
        ),
        "critico": (
            "• Aplicar nematicidas biológicos o químicos (según análisis de suelo y etiqueta).\n"
            "• Implementar solarización o biofumigación.\n"
            "• Añadir materia orgánica para mejorar estructura del suelo."
        ),
        "leve": (
            "• Incorporar compost y rotar con gramíneas o leguminosas no hospedantes.\n"
            "• Controlar riego excesivo y evitar compactación del terreno."
        ),
        "sano": (
            "• Mantener prácticas preventivas de rotación y buen drenaje.\n"
            "• Uso de microorganismos benéficos en suelo."
        ),
    },
}
