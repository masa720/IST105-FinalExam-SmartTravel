from django.db import models

class TravelQuery(models.Model):
    start_city = models.CharField(max_length=100)
    end_city = models.CharField(max_length=100)
    timestamp = models.DateTimeField(auto_now_add=True)
    route_summary = models.TextField()

    def __str__(self):
        return f"From {self.start_city} to {self.end_city} at {self.timestamp}"
