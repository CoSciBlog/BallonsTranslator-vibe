[简体中文](../doc/团子OCR说明.md) | [pt-BR](/Manual_TuanziCR_pt_BR.md) | [Español](../doc/Manual_TuanziOCR_ES.md) | Français

## Référence des paramètres de requête (Officielle)

<p align="center">
    <img src="https://github.com/PiDanShouRouZhouXD/BallonsTranslator/assets/38401147/3c3985e9-f36e-41fb-af94-d6a8088e5ccd" width="85%" height="85%">
</p>

## Description de Tuanzi OCR

### Connexion
Lors de votre première connexion, vous pourriez recevoir des messages d’erreur concernant le mot de passe. Si vous êtes certain que le mot de passe est correct, cochez puis décochez l’option « force_refresh_token » pour forcer une nouvelle connexion. Enregistrez les paramètres et le problème devrait être résolu.

### Détection de texte
La fonction de détection de texte extrait également du texte, mais de manière holistique (identification complète). Ainsi, lors de l’utilisation de TuanziOCR, il est recommandé de ne pas se limiter uniquement à la fonction OCR, mais de combiner la détection de texte de TuanziOCR avec l’option « none_ocr ». TuanziOCR dispose de filtres intégrés pour les onomatopées (reproduction de sons au moyen de phonèmes ou de mots. Exemples : bruits, cris, sons d’animaux, etc.) ainsi que d’autres fonctionnalités. Pour connaître les réglages détaillés, veuillez consulter la « Référence des paramètres de requête (officielle) » ci-dessus.