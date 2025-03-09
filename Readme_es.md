# Open Library

![Python Build](https://github.com/internetarchive/openlibrary/actions/workflows/python_tests.yml/badge.svg)
![JS Build](https://github.com/internetarchive/openlibrary/actions/workflows/javascript_tests.yml/badge.svg)
[![Únete al chat en https://gitter.im/theopenlibrary/Lobby](https://badges.gitter.im/theopenlibrary/Lobby.svg)](https://gitter.im/theopenlibrary/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
[![Ábrelo en Gitpod](https://img.shields.io/badge/Contribute%20with-Gitpod-908a85?logo=gitpod)](https://gitpod.io/#https://github.com/internetarchive/openlibrary/)
[![Contribuidores](https://img.shields.io/github/contributors/internetarchive/openlibrary.svg)](https://github.com/internetarchive/openlibrary/graphs/contributors)

[Open Library](https://openlibrary.org) un catálogo de biblioteca abierto y editable, que se construye con el objetivo de crear una página web para todo libro que ha sido publicado

¿Estás buscando comenzar? [Esta es la guía](https://github.com/internetarchive/openlibrary/blob/master/CONTRIBUTING.md) que estas buscando. Tal vez te gustaría saber más del programa [Google Summer of Code (GSoC)?](https://github.com/internetarchive/openlibrary/wiki/Google-Summer-of-Code) o del  [Hacktoberfest](https://github.com/internetarchive/openlibrary/wiki/Hacktoberfest).

## Tabla de Contenidos
   - [Descripción](#Descripción)
   - [Instalación](#Instalación)
   - [Organización del Código](#Organización-del-Código)
   - [Arquitectura](#Arquitectura)
     - [El Frontend](https://github.com/internetarchive/openlibrary/wiki/Frontend-Guide)
     - [El Backend](#el-backend)
     - [La Arquitectura del Servicio](https://github.com/internetarchive/openlibrary/wiki/Production-Service-Architecture)
   - [Guía de Desarrollador](#Guía-de-Desarrollador)
   - [Ejecución de Pruebas](#Ejecución-de-Pruebas)
   - [Cómo Contribuir](#Cómo-Contribuir)
   - [APIs Públicas](https://openlibrary.org/developers/api)
   - [Preguntas Frecuentes](https://openlibrary.org/help/faq)

## Descripción

Open Library es un esfuerzo empezado en el 2006 para crear "una página web para todo libro que ha sido publicado." Esta provee acceso a múltiples libros de dominio público y descatalogados que pueden leerse en línea.

Aquí tienes un recorrido público y rápido de Open Library para que te puedas familiarizar con el servicio y lo que ofrece (10min).

[![archive org_embed_openlibrary-tour-2020 (1)](https://user-images.githubusercontent.com/978325/91348906-55940d00-e799-11ea-83b9-17cd4d99642b.png)](https://archive.org/embed/openlibrary-tour-2020/openlibrary.ogv)

- [Conoce más del proyecto Open Library](https://openlibrary.org/about)
- [La Visión (El Sueño) de  Open Library](https://openlibrary.org/about/vision)
- [Visita el Blog](https://blog.openlibrary.org)

## Instalación

Ejecuta `docker compose up` y visita http://localhost:8080

¿Necesitas más detalles? Checa las [Instrucciones de Docker](https://github.com/internetarchive/openlibrary/blob/master/docker/README.md)
o el [video tutorial](https://archive.org/embed/openlibrary-developer-docs/openlibrary-docker-set-up.mp4).

***Alternativamente***, Si no quieres montar Open Library en tu computadora local, prueba Gitpod! 
Esto te deja trabajar en Open Library enteramente desde tu navegador sin tener que instalar nada en tu computadora personal.
Advertencia: Esta integración sigue siendo experimental.
[![Ábrelo en Gitpod](https://img.shields.io/badge/Contribute%20with-Gitpod-908a85?logo=gitpod)](https://gitpod.io/#https://github.com/internetarchive/openlibrary/)

### Guía de Desarrollador

También puedes encontrar más información sobre la Documentación para Desarrolladores de Open Library en la [Wiki](https://github.com/internetarchive/openlibrary/wiki/) de Open Library.

## Organización del Código

* openlibrary/core - funcionalidad central de Open Library, importada y utilizada por www
* openlibrary/plugins - otros modelos, controladores y ayudantes de vista (view helpers)
* openlibrary/views - vistas para renderizar páginas web
* openlibrary/templates - todas las plantillas utilizadas en el sitio web
* openlibrary/macros - los macros son similares a las plantillas, pero pueden ser llamados desde wikitext

## Arquitectura

### El Backend

OpenLibrary es desarrollado sobre el sistema wiki Infogami, que a su vez está construido sobre el framework web.py de Python y el framework de base de datos Infobase.

- [Descripción General de las Tecnologías Web Backend](https://openlibrary.org/about/tech)

Una vez que hayas leído la descripción general de las tecnologías Backend de OpenLibrary, es sumamente recomendable que leas la guía básica para desarrolladores, la cual explica como usar Infogami (y su base de datos, Infobase).

- [Tutorial para Desarrolladores de Infogami](https://openlibrary.org/dev/docs/infogami)

Si quieres profundizar en el código fuente de Infogami, consulta el [repo de Infogami](https://github.com/internetarchive/infogami).

## Ejecución de Pruebas

Las pruebas de Open Library puedes ser ejecutadas usando docker. Consulta nuestro [Documento de Pruebas](https://github.com/internetarchive/openlibrary/wiki/Testing) para más detalles.

```
docker compose run --rm home make test
```

## Cómo Contribuir

Hay muchas formas en las cuales voluntarios pueden contribuir al proyecto Open Library, desde el desarrollo y diseño hasta la gestión de datos y la participación de la comunidad. De estas formas puedes involucrarte:

### Desarrolladores
- **Empezando:** Checa nuestra [Guía de Contribuciones](https://github.com/internetarchive/openlibrary/blob/master/CONTRIBUTING.md) para tener instrucciones de como configurar tu entorno de desarrollo, encuentra issues en los cuales trabajar, y envia tus contribuciones.
- **Buen Primer Issue (Good First Issues):** Explora nuestros [Good First Issues](https://github.com/internetarchive/openlibrary/issues?q=is%3Aissue+is%3Aopen+-linked%3Apr+label%3A%22Good+First+Issue%22+no%3Aassignee) para encontrar tareas sencillas para principiantes.

### Diseñadores
- **Contribuciones de Diseño:** Son bienvenidos los diseñadores que deseen ayudar a mejorar la experiencia del usuario. Pueden comenzar revisando [issues relacionados con diseño](https://github.com/internetarchive/openlibrary/labels/design).

### Bibliotecarios y entusiastas de los datos
- **Contribuciones de Datos:** Aprende como contribuir a nuestro catálogo y ayudar a mejorar la información sobre libros en Open Library. Visita nuestra [página de voluntarios](https://openlibrary.org/volunteer) para más información.

### Participación Comunitaria
- **Únete a nuestras Llamadas Comunitarias:** Open Library organiza llamadas semanales de comunidad y diseño. Checa el [Planograma de llamadas comunitarias](https://github.com/internetarchive/openlibrary/wiki/Community-Call) para tiempos y detalles.
- **Pregunta:** Si tienes cualquier duda, únete a nuestro [chat de gitter](https://gitter.im/theopenlibrary/Lobby) o pide una invitación a nuestro canal de Slack en nuestra [página de voluntarios](https://openlibrary.org/volunteer).

Para información más detallada, consulta la [Guía de Contribuciones](https://github.com/internetarchive/openlibrary/blob/master/CONTRIBUTING.md).


## Licencia

Todo el código fuente publicado aqui esta disponible bajo los términos de la licencia [GNU Affero General Public License, version 3](https://www.gnu.org/licenses/agpl-3.0.html).
