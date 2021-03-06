import datetime
import os
import logging

from django.db import transaction

import gpxpy

from . import models

class WorkoutAlreadyExists(Exception):
    pass

def _workout_already_exists(user, started, finished):
    try:
        models.Workout.objects.get(user=user, started=started, finished=finished)
        logging.debug("workout already exists")
        return True
    except:
        logging.debug("workout not there")
        return False


def upload_gpx(request):
    content = request.FILES['gpxfile'].read().decode('utf-8')
    save_gpx(request.user, content)


def save_gpx(user, content):
    logging.debug("saving gpx")

    parsed = gpxpy.parse(content)

    started, finished = parsed.get_time_bounds()
    if _workout_already_exists(user, started, finished):
        raise WorkoutAlreadyExists()

    started, finished = parsed.get_time_bounds()

    workout = models.Workout.objects.create(user=user,
                                            started=started,
                                            finished=finished)

    gpx = models.Gpx.objects.create(workout=workout,
                                    activity_type = parsed.tracks[0].type,
                                    length_2d = int(parsed.length_2d()),
                                    length_3d = int(parsed.length_3d()))

    for track in parsed.tracks:
        for segment in track.segments:
            for point in segment.points:
                gpx.gpxtrackpoint_set.create(lat=point.latitude,
                                             lon=point.longitude,
                                             hr=point.extensions.get('hr', None),
                                             cad=point.extensions.get('cad', None),
                                             time=point.time)

import endoapi.endomondo

@transaction.atomic
def _import_endomondo_workout(user, endomondo_workout):
    workout = models.Workout.objects.create(user=user,
                                            started=endomondo_workout.start_time,
                                            finished=endomondo_workout.start_time + endomondo_workout.duration)

    models.EndomondoWorkout.objects.create(workout=workout,
                                           endomondo_id=endomondo_workout.id)

    gpx = models.Gpx.objects.create(workout=workout,
                                    activity_type = endomondo_workout.sport,
                                    length_2d = endomondo_workout.distance)

    for point in endomondo_workout.points:
        gpx.gpxtrackpoint_set.create(lat=point['lat'],
                                     lon=point['lon'],
                                     hr=point.get('hr', None),
                                     cad=point.get('cad', None),
                                     time=point['time'])


def synchronize_endomondo(user):
    key = models.AuthKeys.objects.get(user=user, name="endomondo")
    endomondo = endoapi.endomondo.Endomondo(token=key.key)

    for endomondo_workout in endomondo.get_workouts():
        if not _workout_already_exists(user,
                                       endomondo_workout.start_time,
                                       endomondo_workout.start_time + endomondo_workout.duration):
            _import_endomondo_workout(user, endomondo_workout)


def connect_to_endomondo(user, email, password):
    endomondo = endoapi.endomondo.Endomondo(email=email, password=password)
    token = endomondo.token
    models.AuthKeys.objects.update_or_create(defaults={'key': token}, user=user, name="endomondo")


def endomondo_key(user):
    try:
        return models.AuthKeys.objects.get(user=user, name="endomondo")
    except:
        return None


def disconnect_endomondo(user):
    models.AuthKeys.objects.get(user=user, name="endomondo").delete()


def purge_endomondo_workouts(user):
    models.Workout.objects.filter(user=user, endomondoworkout__isnull=False).delete()
