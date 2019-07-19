from __future__ import absolute_import

from celery import Celery

app = Celery('snowcover_gpl')

# Celery settings
app.conf.accept_content = ['json','pickle']
app.conf.task_serializer= 'json'
app.conf.result_serializer = 'json'
app.conf.timezone = 'Europe/Zurich'
app.conf.broker_url = "redis://redis:6379/" #Connected to a redis container called redis in the standard port
#app.conf.result_backend= 'redis://redis:6379/'
app.conf.broker_pool_limit = 1
app.conf.broker_heartbeat = None # We're using TCP keep-alive instead
app.conf.broker_connection_timeout = 30 # May require a long timeout due to Linux DNS timeouts etc
app.conf.worker_send_task_events = True # Will create celeryev.* queues
app.conf.event_queue_expires = 60 # Will delete all celeryev. queues without consumers after 1 minute.
app.conf.worker_prefetch_multiplier = 1 # Disable prefetching, it's causes problems and doesn't help performance
app.conf.worker_concurrency = 50 # If you tasks are CPU bound, then limit to the number of cores, otherwise increase substainally
app.conf.chord_unlock_max_retries = 10 # https://github.com/celery/celery/issues/1700#issuecomment-317061500

app.conf.update(
     CHORD_UNLOCK_MAX_RETRIES=10,
)

#if we add tasks in a module, we have to remember to route them here. For the momment the queues are 
#selected by module "<modulename>.<task file>.*". We can do it more granularly if we want, but it should be enough
app.conf.task_routes = {
   'snowcover_gpl.tasks.*': {'queue': 'snowcover_gpl'},
   'snowcover.tasks.*': {'queue': 'snowcover'},
   'core_app.tasks.*': {'queue': 'django'},
   'api_app.tasks.*': {'queue': 'django'},
}

#just in case we forget to add some module's tasks to an specific queue
app.conf.task_default_queue = 'snowcover_gpl'

#autodiscover tasks (as this instance of celery is not managed by django, we have to specify the modules to look into)
app.autodiscover_tasks(['snowcover_gpl'])


if __name__ == '__main__':
   app.start()