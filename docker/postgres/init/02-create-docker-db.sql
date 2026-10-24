-- Base de datos del entorno completo (`docker compose up`). Va separada de la de desarrollo
-- (`docintel`) porque cada entorno guarda los PDF en un sitio distinto: compartir la base
-- dejaría documentos cuyo archivo no existe en el otro entorno.
CREATE DATABASE docintel_docker OWNER docintel;
