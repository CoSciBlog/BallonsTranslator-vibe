[简体中文](../doc/团子OCR说明.md) | [pt-BR](/Manual_TuanziCR_pt_BR.md) | Español | [Français](../doc/Manual_TuanziOCR_FR.md)

## Parámetros de solicitud Referencia (Oficial)

<p align="center">
<img src="https://github.com/PiDanShouRouZhouXD/BallonsTranslator/assets/38401147/3c3985e9-f36e-41fb-af94-d6a8088e5ccd" width="85%" height="85%">
</p>

## Descripción de Tuanzi OCR

### Inicio de sesión
Cuando te conectes por primera vez, es posible que recibas mensajes de error sobre la contraseña. Si estás seguro de que la contraseña es correcta, marca y desmarca la opción "force_refresh_token" para forzar un nuevo inicio de sesión. Guarda la configuración y el problema debería resolverse.

### Detección de texto
La función de detección de texto también extrae texto, pero de forma holística (identificación completa). Por lo tanto, al utilizar TuanziOCR, recomendamos no utilizar únicamente la función de OCR, sino combinar la detección de texto de TuanziOCR con la opción "none_ocr". TuanziOCR tiene filtros integrados para onomatopeyas (Reproducción de sonidos por medio de fonemas/palabras. Algunos ejemplos: Ruidos, gritos, sonidos de animales, etc.) y otras funciones. Para conocer los ajustes detallados, consulte la "Referencia de parámetros de solicitud (oficial)" anterior.