#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    Palmprint Scanner
    =================


    :authors: L. Basedow, L. Gillner, J. Prothmann, C. Werner
    :version: 1.0
    :license: GPLv3
    :format: black, reST docstrings
"""

import sys
import base64
import os


from typing import Union
from collections import namedtuple

import numpy as np
import cv2 as cv

from sqlalchemy import create_engine
from sqlalchemy import Column, Integer, String, ForeignKey

from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.orm import sessionmaker

from scipy.spatial import distance


# Verbindung zur Datenbank
engine = create_engine("sqlite:///palmprint.db")

# Datenmodell laden
Base = declarative_base()

# Session für Datenbankzugriff erzeugen
Session = sessionmaker(bind=engine)
session = Session()


# # # # # # #
# Constants #
# # # # # # #


THRESH_FACTOR = 0.5
THRESH_SUBIMG = 150.0
THRESH_CON = 15
THRESH_HAMMING = 0.43

GAMMA = 10
G_L = 23 / 32
G_U = 31 / 32

GABOR_KSIZE = (35, 35)
GABOR_SIGMA = 5.6179
GABOR_THETAS = np.arange(0, np.pi, np.pi / 32)
GABOR_LAMBDA = 1 / 0.0916
GABOR_GAMMA = 0.7  # 0.23 < gamma < 0.92
GABOR_PSI = 0
GABOR_THRESHOLD = 150  # 0 to 255

# 110 etwas zu hoch
MASK_THRESHOLD = 85

ROI_RAD = 75

SHREKD = False

# Farben
C_NORM = "\033[0m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"

# Sonderzeichen
mark_check = C_GREEN + "✔️" + C_NORM
mark_fail = C_RED + "✗" + C_NORM


# # # # # #
# Models  #
# # # # # #


class User(Base):
    """
    Klasse für registrierte Nutzer in der Datenbank, damit beim
    Matching der Hand eine Identität zugeordnet werden kann.

    :attr __tablename__: Name der Tabelle in der echten Datenbank.
    :attr id: Primary Key Identifier jedes Palmprints;
        Auto-Increment, wird von der Datenbank selbst gesetzt.
    :attr name: Name des Nutzers.
    :attr palmprints: Liste aus Palmprints, die zu dieser ID gehören;
        wird von SQLAlchemy gesetzt, BITTE NICHT MANUELL ÄNDERN!
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    palmprints = relationship("Palmprint", backref="user")

    def __repr__(self):
        return "<{} {} '{}', {} prints registered>".format(
            self.__class__.__name__, self.id, self.name, len(self.palmprints)
        )


class Palmprint(Base):
    """
    Klasse für Palmprints. Palmprints werden separat vom Nutzer
    gespeichert, da so sowohl eine beliebige Anzahl von Prints
    pro Nutzer möglich ist. Dank SQLAlchemy bleibt die Beziehung
    zwischen Nutzern und ihren Prints erhalten, sodass sowohl von
    Nutzern auf ihre enrollten Prints, als auch von Prints zu den
    zugehörigen Nutzern referenziert werden kann.

    :attr __tablename__: Name der Tabelle in der echten Datenbank.
    :attr id: Primary Key Identifier jedes Palmprints;
        Auto-Increment, wird von der Datenbank selbst gesetzt.
    :attr user_id: ID eines bereits existierenden Nutzers.
    :attr roi: Nur der ROI-Ausschnitt des Palmprints; Base64-kodiert.
    :attr original: Das Originalbild als Fallback, falls an der ROI
        einmal was geändert werden soll; Base64-kodiert.
    """

    __tablename__ = "palmprints"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    roi = Column(String)
    mask = Column(String)
    original = Column(String)

    @staticmethod
    def encode(img: np.ndarray) -> bytes:
        """
        Numpy 2D-Array als Base64-String kodieren.

        :param img: Eingangsbild
        :returns: Bild als Base64 PNG-Bild
        """
        _, png_img = cv.imencode(".png", img)
        b64_img = base64.b64encode(png_img)

        return b64_img

    @staticmethod
    def decode(b64_img: str) -> np.ndarray:
        """
        Base64-String zu Numpy-Array konvertieren.

        :param b64_img: das kodierte Bild
        :returns: Array, mit dem dem OpenCV arbeiten kann
        """
        imgarray = np.frombuffer(base64.b64decode(b64_img), np.uint8)
        img = cv.imdecode(imgarray, cv.IMREAD_GRAYSCALE)

        return img

    def get_roi(self) -> np.ndarray:
        """
        ROI Getter.

        :returns: ROI als Numpy-Matrix
        """
        return self.decode(self.roi)

    def get_mask(self) -> np.ndarray:
        """
        ROI Getter.

        :returns: ROI als Numpy-Matrix
        """
        return self.decode(self.mask)

    def get_original(self):
        """
        Getter für Originalbild, aus dem die ROI extrahiert wurde.

        :returns: Bild als Numpy-Matrix
        """
        return self.decode(self.original)

    def __repr__(self):
        return "<{} {} (user {})>".format(
            self.__class__.__name__, self.id, self.user_id
        )


# wenn db nicht vorhanden, lege eine an
Base.metadata.create_all(engine)


# # # # # # #
# DB Access #
# # # # # # #


def create_user(name: str, palmprints: list):
    """
    Anlegen eines neuen Nutzers mit beliebig vielen Palmprints.

    :param name: Name des neuen Nutzers
    :param palmprints: Liste aus anzulegenden Palmprints als Tupel (roi, original)
    :returns: None
    """
    # neue Nutzerinstanz anlegen
    user = User(name=name)
    session.add(user)
    # Nutzer vorläufig in die DB schreiben, um eine ID zu bekommen
    session.flush()

    for pp in palmprints:
        roi = Palmprint.encode(pp[0])
        original = Palmprint.encode(pp[1])
        mask = Palmprint.encode(pp[2])
        palmprint = Palmprint(user_id=user.id, roi=roi, mask=mask, original=original)
        session.add(palmprint)

    # Neue Daten endgültig in die DB schreiben
    session.commit()


def list_users():
    """Ausgabe aller Nutzer."""
    users = session.query(User).all()
    for u in users:
        print(u)


def get_users() -> list:
    """
    Abfrage aller Nutzer.

    :returns: Nutzer-Objekt
    """
    users = session.query(User).all()

    return users


def get_user(user_id: int) -> User:
    """
    Abfrage eines einzelnen Nutzers.

    :param user_id: ID des Nutzers
    :returns: Nutzer-Objekt
    """
    user = session.query(User).filter_by(id=user_id).one_or_none()

    if user is None:
        raise Exception("Cannot query user {}: no such user!".format(user_id))

    return user


def delete_user(user_id: int):
    """
    Löschen eines bestehenden Nutzers samt zugeordneter Palmprints.

    :param user_id: ID des zu löschenden Nutzers
    :returns: None
    """
    user = session.query(User).filter_by(id=user_id).one_or_none()

    if user is None:
        raise Exception("Cannot delete user {}: no such user!".format(user_id))

    palmprints = session.query(Palmprint).filter_by(user_id=user_id).all()

    for pp in palmprints:
        session.delete(pp)

    session.delete(user)
    session.commit()


def insert_palmprints(user_id: int, palmprints: list):
    """
    Einfügen neuer Palmprints (1 bis N) zu bestehendem Nutzer.

    :param user_id: ID des Nutzers
    :param palmprints: Liste aus Tupeln der Form (roi, original), beides np.ndarrays
    :returns: None
    """
    user = session.query(User).filter_by(id=user_id).one_or_none()

    if user is None:
        raise Exception("Cannot insert palmprint for {}: no such user!".format(user_id))

    for pp in palmprints:
        roi = Palmprint.encode(pp[0])
        original = Palmprint.encode(pp[1])
        palmprint = Palmprint(user_id=user.id, roi=roi, original=original)
        session.add(palmprint)

    session.commit()


def update_palmprint(palmprint_id: int, roi=None, original=None, mask=None):
    """
    Update eines bereits bestehenden Palmprints.

    :param palmprint_id: ID des Palmprints
    :param roi: extrahierte ROI
    :param original: Originalbild
    :param mask: Maske zur ROI
    :returns: None
    """
    palmprint = session.query(Palmprint).filter_by(id=palmprint_id).first()

    if palmprint is None:
        raise Exception(
            "Cannot update palmprint {}: no such palmprint!".format(palmprint_id)
        )

    if roi is not None:
        new_roi = Palmprint.encode(roi)
        palmprint.roi = new_roi

    if original is not None:
        new_original = Palmprint.encode(original)
        palmprint.original = new_original

    if mask is not None:
        new_mask = Palmprint.encode(mask)
        palmprint.mask = new_mask

    session.commit()


def delete_palmprint(palmprint_id: int):
    """
    Löschen eines bestehenden Palmprints.

    :param palmprint_id: Palmprint ID
    :returns: None
    """
    palmprint = session.query(Palmprint).filter_by(id=palmprint_id).one_or_none()

    if palmprint is None:
        raise Exception(
            "Cannot delete palmprint {}: no such palmprint!".format(palmprint_id)
        )

    session.delete(palmprint)
    session.commit()


def get_user_palmprints(username: str) -> list:
    """
    Suche alle Palmprints die dem Usernamen zugeordnet sind.

    :param username: String
    :returns: alle Palmprints des Users in einer Liste
    """
    user = session.query(User).filter_by(name=username).one_or_none()
    palmprints = user.palmprints

    return palmprints


def get_palmprints() -> list:
    """
    Suche alle Palmprints in der Datenbank.

    :returns: alle Palmprints in einer Liste
    """
    palmprints = session.query(Palmprint).all()

    palmprints = [pp.get_roi() for pp in palmprints]

    return palmprints


# # # # # #
# Utility #
# # # # # #


def progress(current: int, maximum: int):
    """
    Zeige den aktuellen Fortschitt beim Loopen
    über eine Liste in Prozent.

    :param current: aktuelle Position im Loop
    :param maximum: höchster Index im Loop
    """
    current += 1
    prog = int(100 * (current / maximum))

    print(f"{prog}%", end="\r")

    if current == maximum:
        print()


def load_img(path: str) -> np.ndarray:
    """
    Wrapper um cv.imread(), damit auch wirklich immer
    Graustufenbilder eingelesen werden.

    :param path: Dateipfad
    :returns: Bild als 2D Numpy Array
    """
    if os.path.exists(path):
        img = cv.imread(path, cv.IMREAD_GRAYSCALE)

        return img
    else:
        raise Exception("Angegebener Pfad nicht vorhanden!")


def interpol2d(points: list, steps: int) -> list:
    """
    Interpoliere steps Punkte auf Basis von points.

    :param points: Liste aus Punkten (Tupel)
    :param steps: Anzahl der Schritte
    :returns: interpolierte Punkte in einer Liste
    """
    x = np.array([p[0] for p in points])
    y = np.array([p[1] for p in points])
    i = np.arange(len(points))
    s = np.linspace(i[0], i[-1], steps)

    return list(zip(np.interp(s, i, x), np.interp(s, i, y)))


def find_tangent_points(v_1: list, v_2: list) -> Union[tuple, tuple]:
    """
    Prüfe für jeden Punkt P in einem Tal (Kurve K), ob eine Gerade zwischen P
    und einem Punkt auf der anderen Kurve eine Tangente beider Kurven ist.
    Wenn ja, gib jeweils die Punkte beider Kurven zurück, die auf der Tangente liegen.

    :param v_1: erste zu betrachtende Kurve (Listen aus Koordinatentupeln)
    :param v_2: zweite zu betrachtende Kurve (Listen aus Koordinatentupeln)
    :returns: Punkte der Tangente bei Existenz, None andernfalls
    """
    vs = v_1 + v_2

    # wenn die Gerade zwischen p_1 und p_2 keine weiteren Punkte in v_1 und v_2 schneidet,
    # dann ist die Gerade als Tangente beider Kurven anzusehen
    for p_1 in v_1:
        for p_2 in v_2:
            # Wahrheitskriterium soll auf alle p aus v_1 und v_2 zutreffen
            if all(
                [
                    # ist f(p.y) größer als p.x, d.h. existiert kein Schnittpunkt?
                    # f sei die Geradengleichung der Geraden zw. p_1 und p_2
                    (
                        p_1[0] * ((p[1] - p_2[1]) / (p_1[1] - p_2[1]))
                        + p_2[0] * ((p[1] - p_1[1]) / (p_2[1] - p_1[1]))
                    )
                    >= p[0]
                    for p in vs
                ]
            ):
                # runde Koordinaten zu nächsten ganzzahligen Pixelwerten
                p_1 = (int(np.round(p_1[0])), int(np.round(p_1[1])))
                p_2 = (int(np.round(p_2[0])), int(np.round(p_2[1])))
                return p_1, p_2

    return None, None


def left_right_detector(valleys: list) -> str:
    """
    Finde heraus, ob es sich bei den Valleys um Koordinaten einer linken
    oder rechten Hand handelt.

    :param valleys: Liste aus Koordinatentupeln
    :returns: "l", "r" oder None, wenn etwas nicht stimmt
    """
    retval = None

    midpoints = [(v[int(len(v) / 2)][0], v[int(len(v) / 2)][1]) for v in valleys]

    dists = []

    for i in range(1, len(midpoints), 1):
        dists.append(
            np.linalg.norm(np.array(midpoints[i]) - np.array(midpoints[i - 1]))
        )

    idx_max = dists.index(max(dists))

    if idx_max == 1:
        retval = "r"
    elif idx_max == len(valleys) - 1:
        retval = "l"

    return retval


# # # # # # # # #
# Preprocessing #
# # # # # # # # #


def neighbourhood_curvature(
    p: tuple, img: np.ndarray, n: int, r: int, inside: int = 255
) -> float:
    """
    Überprüfe n Nachbarn im Abstand von r, ob sie innerhalb oder außerhalb
    der Fläche im Bild img liegen, ausgehend von Punkt p.
    Anhand dessen kann festgestellt werden, ob es sich um eine Kurve handelt.

    :param p: Koordinatenpunkt
    :param img: Binärbild
    :param n: Anzahl der Nachbarn
    :param r: Abstand der Nachbarn
    :param inside: Farbe, die als "innen" qualifiziert
    :returns: "Kurvigkeit"
    """
    # Randbehandlung; Kurven in Bildrandgebieten sind nicht relevant!
    if (
        p[0] == 0
        or p[1] == 0
        # p[]+r nicht innerhalb von img-Dimensionen
        or p[0] + r >= img.shape[1]
        or p[0] - r < 0
        or p[1] + r >= img.shape[0]
        or p[1] - r < 0
    ):
        return 0.0
    else:
        stepsize = int(360 / n)
        neighvals = []

        for a in range(0, 90, stepsize):
            d_y = np.round(np.cos(np.deg2rad(a)), 2)
            d_x = np.round(np.sin(np.deg2rad(a)), 2)
            y_p = int(np.round(p[1] - (r * d_y)))
            y_n = int(np.round(p[1] + (r * d_y)))
            x_p = int(np.round(p[0] + (r * d_x)))
            x_n = int(np.round(p[0] - (r * d_x)))

            neighvals.extend(
                (img[y_p, x_p], img[y_n, x_p], img[y_n, x_n], img[y_p, x_n])
            )

        return (sum(neighvals) / inside) / n


def find_valleys(img: np.ndarray, contour: list) -> list:
    """
    Kombiniert den CHVD-Algorithmus (Ong et al.) mit einfachem Mask-Matching
    und findet so die "Täler" in einer Kontur.

    :param img: Bild, in dem die Täler gesucht werden
    :param contour: Kontur des Bildes als Punkteliste
    :returns: Täler als Liste aus Listen von Punkten (nach Zusammenhängen gruppiert)
    """
    valleys = []
    last = 0
    idx = -1

    # durchlaufe die Punkte auf der Kontur
    for i, c in enumerate(contour):
        # quadratischer Bildausschnitt der Seitenlänge GAMMA mit c als Mittelpunkt
        subimg = img[c[1] - GAMMA : c[1] + GAMMA, c[0] - GAMMA : c[0] + GAMMA]
        if (
            len(subimg) > 0
            and (G_L <= neighbourhood_curvature(c, img, 32, GAMMA) <= G_U)
            and subimg.mean() >= THRESH_SUBIMG
        ):
            # prüfe auf mögl. Zusammenhang mit vorheriger Gruppe; starte neue Gruppe,
            # wenn der Abstand zu groß ist
            if i - last > THRESH_CON:
                idx += 1
                valleys.append([c])
            else:
                valleys[idx].append(c)
            last = i

    return valleys


def find_keypoints(valleys: list) -> Union[tuple, tuple]:
    """
    Finde die Keypoints des Bildes, in unserem Fall die beiden Lücken
    zwischen Zeige und Mittelfinger bzw. Ring- und kleinem Finger.

    :param valleys: Liste von gefundenen Valleys
    :returns: Koordinaten der Keypoints
    """
    if len(valleys) < 2:
        raise Exception("Expected at least 2 valleys!")

    # schmeiße 1er-Längen raus, sind meistens Fehler
    valleys = [v for v in valleys if len(v) > 1]
    # test ob überhaupt noch valleys vorhanden sind
    if valleys.__len__() == 0:
        raise Exception("No valleys found!")

    # sortiere die Täler nach ihrer y-Koordinate
    valleys.sort(key=lambda v: v[0][1])

    # Werte interpolieren, um eine etwas sauberere Kurve zu bekommen
    valleys_interp = [interpol2d(v, 10) for v in valleys]

    # im Optimalfall sollten erster und letzter Punkt die Keypoints sein
    v_1 = valleys_interp[0]
    v_2 = valleys_interp[-1]

    # Punkte auf Tangente beider Täler finden; das sind die Keypoints
    kp_1, kp_2 = find_tangent_points(v_1, v_2)

    # TODO: Test this exception
    if kp_1 is None or kp_2 is None:
        raise Exception("Couldn't find a tangent for {} and {}!".format(kp_1, kp_2))

    return kp_1, kp_2


def transform_to_roi(img: np.ndarray, p_min: tuple, p_max: tuple) -> np.ndarray:
    """
    Transformiere Bild so, dass Punkte p_min und p_max
    die y-Achse an der linken Bildkante bilden.

    :param img: Eingangsbild
    :param p_min: Minimum des Koordinatensystems
    :param p_max: Maximum des Koordinatensystems
    :returns: gedrehtes und auf "y-Achse" beschnittenes Bild
    """
    # berechne notwendige Abstände
    a = p_max[0] - p_min[0]
    b = p_min[1] - p_max[1]
    angle = np.rad2deg(np.arctan(a / b))

    # rotiere Bild um p_min
    rot_mat = cv.getRotationMatrix2D(p_min, angle, 1.0)
    rotated = cv.warpAffine(img, rot_mat, img.shape[1::-1])

    # beschneide das Bild auf ROI; y_mid ist die halbe Strecke zw. p_min und p_max
    y_mid = p_min[1] - round(np.linalg.norm(np.array(p_max) - np.array(p_min)) * 0.5)
    y_start = y_mid - ROI_RAD
    y_end = y_mid + ROI_RAD
    x_start = p_min[0] + 10
    x_end = x_start + (2 * ROI_RAD)
    cropped = rotated[y_start:y_end, x_start:x_end]

    return cropped


def extract_roi(img: np.ndarray) -> np.ndarray:
    """
    Wrapper für den ROI-Findungsprozess.

    :param img: Bild, aus dem die ROI extrahiert werden soll
    :returns: ROI
    """
    # weichzeichnen und binarisieren
    blurred = cv.GaussianBlur(img, (7, 7), 0)
    _, thresh = cv.threshold(
        blurred, (THRESH_FACTOR * img.mean()), 255, cv.THRESH_BINARY
    )

    # finde die Kontur der Hand; betrachte nur linke Hälfte des Bildes,
    # weil wir dort die wichtigen Kurven erwarten können
    contours, _ = cv.findContours(
        thresh[:, : int(img.shape[1] / 2)], cv.RETR_LIST, cv.CHAIN_APPROX_SIMPLE
    )

    # filtere nur die längste Kontur, um mögl. Störungen zu entfernen
    contour = max(contours, key=lambda c: len(c))

    # mach eine Liste aus Tupeln zur besseren Weiterverarbeitung draus
    contour = [tuple(c[0]) for c in contour]

    # "Täler" in der Handkontur finden; dort werden sich Keypoints befinden
    valleys = find_valleys(thresh, contour)

    # beide Keypoints finden
    kp_1, kp_2 = find_keypoints(valleys)

    # Bild um Keypoints rotieren und zuschneiden
    roi = transform_to_roi(img, kp_2, kp_1)

    return roi


# # # # # # #
# Filtering #
# # # # # # #


def build_mask(img: np.ndarray) -> np.ndarray:
    """
    Generiert eine Maske aus dem gegebenen Bild. Schwarze Flächen (kein Teil der Hand) werden maskiert.

    :param img: Bild welches als Grundlage der Maske dienen soll
    :returns: Maske (schwarz/weiß)
    """
    # TODO
    # generiere leeres np array, füllen mit 'weiß' (255)
    mask = np.empty_like(img)
    mask.fill(255)
    # setze jedes Maskenpixel auf 0, wenn im gegebenen Bildpixel der Wert kleiner als
    # der Schwellwert ist
    mask[img < MASK_THRESHOLD] = 0

    return mask


def build_gabor_filters() -> list:
    """
    Generiert eine Liste von Gabor Filtern aus gegebenen Konstanten.

    :returns: Liste von Gabor Filtern
    """
    # ksize - size of gabor filter (n, n)
    # sigma - standard deviation of the gaussian function
    # theta - orientation of the normal to the parallel stripes
    # lambda - wavelength of the sunusoidal factor
    # gamma - spatial aspect ratio
    # psi - phase offset
    filters = []

    for theta in GABOR_THETAS:
        params = {
            "ksize": GABOR_KSIZE,
            "sigma": GABOR_SIGMA,
            "theta": theta,
            "lambd": GABOR_LAMBDA,
            "gamma": GABOR_GAMMA,
            "psi": GABOR_PSI,
            "ktype": cv.CV_32F,
        }
        kern = cv.getGaborKernel(**params)
        filters.append((kern, params))

    return filters


def apply_gabor_filters(img: np.ndarray, filters: list) -> np.ndarray:
    """
    Wendet Filter-Liste auf Bildkopien an, fügt gefilterte Bilder zu einem zusammen
    und entfernt alle Elemente unter einem festgelegten Schwellwert.

    :param img: zu filterndes Bild
    :param filters: Liste von Gabor Filtern
    :returns: gefiltertes Bild
    """
    # generate empty np array and fill it with 'white' (255)
    merged_img = np.empty_like(img)
    merged_img.fill(255)

    # for all filters: filter image and merge with already filtered images
    for kern, params in filters:
        filtered_img = cv.filter2D(img, cv.CV_8UC3, kern)
        np.minimum(merged_img, filtered_img, merged_img)

    # use threshold to remove lines and make it (kind of) binary
    merged_img[merged_img > GABOR_THRESHOLD] = 255
    merged_img[merged_img < GABOR_THRESHOLD] = 0

    return merged_img


def img_to_binary(img: np.ndarray) -> np.ndarray:
    """
    Formt gegebenes Bild in eindimensionales Array um (flatten). Da das gegebene Bild nur aus 0 oder 255
    besteht (siehe apply_gabor_filters()), werden diese in True (1) und False (0) umgewandelt.

    :param img: Bild, das binarisiert werden soll
    :returns:
    """
    flattened = img.flatten()
    flattened[flattened == 0] = True
    flattened[flattened > 1] = False

    return flattened


def hamming_with_masks(
    img1: np.ndarray, mask1: np.ndarray, img2: np.ndarray, mask2: np.ndarray
) -> float:
    """
    Gegebene Masken auf jeweils zugehöriges Bild anwenden.
    Und daraus dann die Hammingdistanz bestimmen.

    :param img1: zu maskierendes Bild (binary 0,1)
    :param mask1: Maske des Bildes (binary 0,1)
    :param img2: zu maskierendes (zweites) Bild (binary 0,1)
    :param mask2: Maske des zweiten Bildes (binary 0,1)
    :returns: Hammingdistanz
    """
    # flatten images and masks
    img1.flatten()
    img2.flatten()
    mask1.flatten()
    mask2.flatten()

    # check if images and masks are binary
    if max(img1) == 1 and max(img2) == 1 and max(mask1) == 1 and max(mask2) == 1:
        # UND-Verknüpfung Masken
        mask_and = np.logical_and(mask1, mask2)
        # XOR-Verknüpfung Bilder
        img_xor = np.logical_xor(img1, img2)
        # UND-Verknüpfung Bildunterschiede und kombinierte Maske
        img_and_mask = np.logical_and(img_xor, mask_and)
        # hamming distance (number of ones in 'masked' divided by length of 'masked')
        # hamming = ((img_and_mask == True).sum()) / (mask_and == True).size
        hamming = ((img_and_mask == True).sum()) / img_and_mask.size
        # print(hamming)

        return hamming

    else:
        raise Exception("values in image and/or mask not binary")


def calculate_hamming(img_to_match: np.ndarray, img_template: np.ndarray) -> float:
    """
    Vergleicht ausgewaehltes Image mit Template Image und berechnet die Hamming Distanz dazwischen.

    :param img_to_match: abzugleichendes, pixelverschobenes Image
    :param img_template: Vorlage, gegen welche gematched wird
    :returns: Hamming Distanz zwischen den Bildern
    """

    # Bibliotheksfunktion zur Sicherheit (Fallback)
    hamming_distance = distance.hamming(
        img_to_binary(img_to_match), img_to_binary(img_template)
    )

    # Berechnung der Hammingdistanz mit AND und XOR von ROIs und Masken
    # bin_img1 = img_to_binary(img_to_match)
    # bin_img2 = img_to_binary(img_template)
    # bin_mask1 = img_to_binary(build_mask(img_to_match))
    # bin_mask2 = img_to_binary(build_mask(img_template))
    # hamming_distance = hamming_with_masks(bin_img1, bin_mask1, bin_img2, bin_mask2)

    return hamming_distance


def matching(img_to_match, img_template) -> float:
    """
    Ausführen des Matching-Algorithmus. Durch Vorgaben wird zuerst eine pixelbasierte
    Translation durchgeführt und anschließend die Hamming Distanz berechnet.

    :param img_to_match: abzugleichendes Image
    :param img_template: Vorlage, gegen welche gematched wird
    :returns: kleinste Hamming Distanz zwischen den Bildern
    """
    # speichert alle Hamming Distanzen
    hamming_distances = []

    # Verschiebungsalgorithmus
    trans_x = [
        -1,
        0,
        1,
        1,
        1,
        0,
        -1,
        -1,
        -2,
        0,
        2,
        2,
        2,
        0,
        -2,
        -2,
    ]  # pos -> rechts & neg -> links
    trans_y = [
        -1,
        -1,
        -1,
        0,
        1,
        1,
        1,
        0,
        -2,
        -2,
        -2,
        0,
        2,
        2,
        2,
        0,
    ]  # pos -> runter & neg -> hoch

    # anwenden der Translation

    for trans in trans_x:
        trans_matrice = [[1, 0, trans_x[trans]], [0, 1, trans_y[trans]]]
        trans_matrice = np.float32(trans_matrice)
        hamming_distances.append(
            translate_image(img_to_match, img_template, trans_matrice)
        )

    # unverschoben
    hamming_distances.append(calculate_hamming(img_to_match, img_template))

    # print(hamming_distances)

    if len(hamming_distances) == 0:
        # return Max Distanz, da keine Distanz berechnet wurde
        return 1.0
    else:
        return min(hamming_distances)


def translate_image(img_to_match, img_template, trans_matrix) -> float:
    """
    Verschiebt zumatchendes Image um die Translationsmatrix.

    :param img_to_match: abzugleichendes Image
    :param img_template: Vorlage, gegen welche gematched wird
    :param trans_matrix: zu nutzende Tranformationsmatrix
    :returns: kleinste Hamming Distanz zwischen den Bildern
    """

    img_slided = cv.warpAffine(
        img_to_match, trans_matrix, (img_to_match.shape[0], img_to_match.shape[1])
    )

    try:
        hamming_distance = calculate_hamming(
            img_slided[2:-2, 2:-2], img_template[2:-2, 2:-2]
        )
    except Exception:
        # set 1.0 bei Default fuer non-Match
        hamming_distance = 1.0

    return hamming_distance


# # # # # # # # # #
# User Management #
# # # # # # # # # #


def enrol(name: str, *palmprint_imgs):
    """
    Enrolment-Prozess. Bekommt nur unverarbeitete Bilder.

    :param name: Name des neuen Nutzers
    :param palmprint_imgs: variable Anzahl von OpenCV-Bildobjekten
    """
    palmprints = []

    if len(palmprints) == 0:
        filters = build_gabor_filters()

        for img in palmprint_imgs:
            roi = extract_roi(img)
            mask = build_mask(roi)
            roi = apply_gabor_filters(roi, filters)
            palmprints.append((roi, img, mask))

    create_user(name, palmprints)


# # # # #
# Main  #
# # # # #


def main():
    """
    Das eigentliche Programm; Bild einlesen und prüfen, ob Print
    zu einem registrierten Nutzer passt.
    Wenn ja, gib den Namen aus.
    """
    if len(sys.argv) != 2:
        print("Aufruf: python3 ppscan.py <pfad/zum/bild>")
        return -1

    file_input = sys.argv[1]

    print("ppscan\n------")
    print("Starte Matching für {} ...".format(os.path.basename(file_input)))

    filters = build_gabor_filters()

    img_input = load_img(file_input)
    roi = extract_roi(img_input)
    filtered_roi = apply_gabor_filters(roi, filters)

    palmprints_list = session.query(Palmprint).all()
    hamming_scores = []

    Match = namedtuple("Match", ["score", "user"])

    for i, palmprint in enumerate(palmprints_list):
        hamming_scores.append(
            Match(
                score=matching(filtered_roi, palmprint.get_roi()),
                user=palmprint.user.name,
            )
        )
        progress(i, len(palmprints_list))

    # minimaler Matching Score
    m_min = min(hamming_scores, key=lambda m: m.score)
    # maximaler Matching Score
    # m_max = max(hamming_scores, key=lambda m: m.score)
    # alle Matching Scores, aufsteigend sortiert
    # hamming_scores.sort(key=lambda m: m.score)

    if m_min.score <= THRESH_HAMMING:
        print(
            "[{0}] Hallo, {1}! Matching Score: {2}".format(
                mark_check, m_min.user.capitalize(), m_min.score
            )
        )
    else:
        if SHREKD:
            print(
                """
                GET OUT OF MY SWAMP\033[92;1m

            ⢀⡴⠑⡄⠀⠀⠀⠀⠀⠀⠀⣀⣀⣤⣤⣤⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀ 
            ⠸⡇⠀⠿⡀⠀⠀⠀⣀⡴⢿⣿⣿⣿⣿⣿⣿⣿⣷⣦⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀ 
            ⠀⠀⠀⠀⠑⢄⣠⠾⠁⣀⣄⡈⠙⣿⣿⣿⣿⣿⣿⣿⣿⣆⠀⠀⠀⠀⠀⠀⠀⠀ 
            ⠀⠀⠀⠀⢀⡀⠁⠀⠀⠈⠙⠛⠂⠈⣿⣿⣿⣿⣿⠿⡿⢿⣆⠀⠀⠀⠀⠀⠀⠀ 
            ⠀⠀⠀⢀⡾⣁⣀⠀⠴⠂⠙⣗⡀⠀⢻⣿⣿⠭⢤⣴⣦⣤⣹⠀⠀⠀⢀⢴⣶⣆ 
            ⠀⠀⢀⣾⣿⣿⣿⣷⣮⣽⣾⣿⣥⣴⣿⣿⡿⢂⠔⢚⡿⢿⣿⣦⣴⣾⠁⠸⣼⡿ 
            ⠀⢀⡞⠁⠙⠻⠿⠟⠉⠀⠛⢹⣿⣿⣿⣿⣿⣌⢤⣼⣿⣾⣿⡟⠉⠀⠀⠀⠀⠀ 
            ⠀⣾⣷⣶⠇⠀⠀⣤⣄⣀⡀⠈⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⠀⠀⠀⠀⠀⠀ 
            ⠀⠉⠈⠉⠀⠀⢦⡈⢻⣿⣿⣿⣶⣶⣶⣶⣤⣽⡹⣿⣿⣿⣿⡇⠀⠀⠀⠀⠀⠀ 
            ⠀⠀⠀⠀⠀⠀⠀⠉⠲⣽⡻⢿⣿⣿⣿⣿⣿⣿⣷⣜⣿⣿⣿⡇⠀⠀⠀⠀⠀⠀ 
            ⠀⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⣷⣶⣮⣭⣽⣿⣿⣿⣿⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀ 
            ⠀⠀⠀⠀⠀⠀⣀⣀⣈⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠇⠀⠀⠀⠀⠀⠀⠀ 
            ⠀⠀⠀⠀⠀⠀⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠃⠀⠀⠀⠀⠀⠀⠀⠀ 
            ⠀⠀⠀⠀⠀⠀⠀⠹⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠟⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀ 
            ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠛⠻⠿⠿⠿⠿⠛⠉\033[0m
                """
            )
        else:
            print(
                "[{0}] Ungültig! Matching Score {1:.5f} ist zu hoch!".format(
                    mark_fail, m_min.score
                )
            )


if __name__ == "__main__":
    sys.exit(main())
