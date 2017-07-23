import math
import pygame
import pygame.locals
import random
import time


# Math constants
HALF_PI = math.pi/2.0
DEGREES_PER_RADIAN = 180.0 / math.pi

# Tuneable physical constants
EMPTY_MASS = 5000               # kilograms
EXHAUST_VELOCITY = 500          # m/s
G = 10.0                        # acceleration due to gravity, m/s^2
MAX_SAFE_LANDING_VELOCITY = 0.1 # meters per second
THROTTLE_MAX = 600              # kg/s
TURN_RATE = 0.2                 # radians per second

MAX_X = 1024
MAX_Y = 768

SPARKS_PER_KG = 0.5
SPARK_LIFETIME = 1 # seconds
SPARK_START_RGBA = (255, 255, 255, 255)
SPARK_END_RGBA = (80, 40, 20, 20)
SPARK_START_RADIUS = 1          # pixels
SPARK_END_RADIUS = 8            # pixels
SPARK_DIRECTION_VARIABILITY = 0.1 # radians
SPARK_VELOCITY_VARIABILITY = 20   # m/s


# This takes a number "s" between 0 and 1 and scales it to be between
# "start" and "end" instead.
def scale(start, end, s):
  result = int(s * (end - start) + start)
  return result


# A Spark is a bit of visible rocket exhaust. It has a short lifetime,
# during which it goes from small and bright to big and dim.
class Spark(object):
  # The list of all sparks, in order of age, with newer ones near the
  # beginning of the list.
  sparks = []

  # Initialize a new spark. We add a little bit of random variability
  # to its starting direction and velocity to get some visual variety
  # in the exhaust plume.
  # TODO: We could also add variability to each spark's lifetime
  # (but that would affect the "sparks" array; see update_all below).
  def __init__(self, position, direction, start_time):
    self.position = position
    direction += random.uniform(-SPARK_DIRECTION_VARIABILITY,
                                SPARK_DIRECTION_VARIABILITY)
    velocity = EXHAUST_VELOCITY + random.uniform(-SPARK_VELOCITY_VARIABILITY,
                                                 SPARK_VELOCITY_VARIABILITY)
    self.velocity = Vector(direction=direction,
                           magnitude=velocity)
    self.start_time = start_time
    self.age = 0

    # Add this new spark to the list of all sparks. It's the newest
    # one, so add it at the beginning.
    self.sparks.insert(0, self)

  def update(self, delta_t):
    x, y = self.position
    x += self.velocity.horizontal_component() * delta_t
    y += self.velocity.vertical_component() * delta_t
    # sparks are affected by gravity too
    self.velocity += Vector(direction=-HALF_PI, magnitude=(G * delta_t))
    self.position = (x, y)

  @classmethod
  def update_all(cls, delta_t, now):
    for i, spark in enumerate(cls.sparks):
      spark.age = (now - spark.start_time) / SPARK_LIFETIME
      if spark.age > 1:
        # As soon as we encounter a spark whose lifetime has expired,
        # we know all the remaining sparks have expired too (since the
        # list is in age-order), so delete them all and break out of
        # the loop.
        # TODO: Add variability to spark lifetimes, so some are
        # longer-lasting than others. Note: that would invalidate the
        # optimization just described.
        del cls.sparks[i:]
        break
      spark.update(delta_t)

  def draw(self, screen):
    radius = scale(SPARK_START_RADIUS, SPARK_END_RADIUS, self.age)
    r, g, b, a = map(lambda start, end: scale(start, end, self.age),
                     SPARK_START_RGBA, SPARK_END_RGBA)
    x, y = map(int, self.position)
    color = pygame.Color(r, g, b, a)
    pygame.draw.circle(screen, color, (x, MAX_Y - y), radius)

  @classmethod
  def draw_all(cls, screen):
    for spark in cls.sparks:
      spark.draw(screen)


# Basic mathematical vector. It has a direction and a magnitude.
class Vector(object):
  def __init__(self, direction=0, magnitude=0):
    self.direction = direction  # radians
    self.magnitude = magnitude

  def horizontal_component(self):
    return self.magnitude * math.cos(self.direction)

  def vertical_component(self):
    return self.magnitude * math.sin(self.direction)

  def __add__(self, other):
    x = self.horizontal_component() + other.horizontal_component()
    y = self.vertical_component() + other.vertical_component()
    return Vector(direction=math.atan2(y, x),
                  magnitude=math.sqrt(x*x + y*y))

  def __str__(self):
    return 'Vector(direction=%f, magnitude=%f)' % (self.direction,
                                                   self.magnitude)


# A ship is an object that keeps track of its position, velocity,
# orientation, throttle setting, rotation speed, and fuel.
class Ship(object):
  def __init__(self):
    self.position = (0, MAX_Y)
    self.velocity = Vector(magnitude=20) # xxx
    self.orientation = 0        # radians; 0 is upright
    self.throttle = 0           # 0..1
    self.rotation = 0           # -1, 0, 1
    self.fuel = 5000            # kg

    self.base_image = pygame.image.load('rainbowbird.png')
    self.image = self.base_image
    self.sprite = pygame.sprite.Sprite()
    self.sprite.image = self.image
    self.sprite.rect = self.sprite.image.get_rect()
    self.sprite_group = pygame.sprite.RenderPlain(self.sprite)

  def draw(self, screen):
    self.sprite.position = (self.position[0], MAX_Y - self.position[1])
    self.sprite.rect.center = self.sprite.position
    self.sprite_group.draw(screen)

  def mass(self):
    return self.fuel + EMPTY_MASS

  def update(self, delta_t, now):
    # update position based on velocity
    x, y = self.position
    x += self.velocity.horizontal_component() * delta_t
    y += self.velocity.vertical_component() * delta_t
    self.position = (x, y)

    # update velocity based on gravity
    self.velocity += Vector(direction=-HALF_PI, magnitude=(G * delta_t))

    # further update velocity (and fuel) based on thrust
    if self.throttle > 0:
      fuel_burned = self.throttle * THROTTLE_MAX * delta_t # units: kilograms
      if fuel_burned > self.fuel:
        fuel_burned = self.fuel # limit fuel_burned to the amount of fuel remaining
        self.fuel = 0
        self.throttle = 0       # running out of fuel sets throttle to 0
      else:
        self.fuel -= fuel_burned
      momentum = fuel_burned * EXHAUST_VELOCITY
      self.velocity += Vector(direction=(self.orientation + HALF_PI),
                              magnitude=(momentum / self.mass()))
      for i in xrange(int(fuel_burned * SPARKS_PER_KG)):
        spark = Spark(self.position, self.orientation - HALF_PI, now)

    # update orientation based on rotation
    if self.rotation:
      self.orientation += self.rotation * TURN_RATE * delta_t
      if self.orientation == 0:
        self.image = self.base_image
      else:
        self.image = pygame.transform.rotate(
          self.base_image, self.orientation * DEGREES_PER_RADIAN)
        self.sprite.image = self.image
      self.sprite.rect = self.sprite.image.get_rect()

  def increase_throttle(self):
    if self.fuel:
      self.throttle += 0.1
      if self.throttle > 1.0:
        self.throttle = 1.0

  def decrease_throttle(self):
    self.throttle -= 0.1
    if self.throttle < 0.0:
      self.throttle = 0

  def set_rotation(self, rotation):
    # TODO: Make changing the rotation rate use up fuel.
    self.rotation = rotation


def main():
  # Initialize the pygame library.
  pygame.init()

  # Create a pygame screen (a pygame.Surface object).
  screen = pygame.display.set_mode((MAX_X, MAX_Y))

  # Create a pygame clock.
  clock = pygame.time.Clock()

  # Create a ship object that keeps track of things like its position,
  # velocity, and fuel. See the definition of the Ship class above.
  ship = Ship()

  # The main loop, which never exits.
  # Each time through the loop is one "frame."
  while True:
    # How much time has elapsed since the last time through the loop?
    delta_t = clock.tick(30) # 30 means "no faster than 30 frames per second"
    delta_t /= 1000.0        # convert milliseconds to seconds for easier math below

    # Update ship physics: position, velocity, fuel, etc.
    ship.update(delta_t, time.time())

    # Update all the "sparks" (the visible rocket exhaust).
    Spark.update_all(delta_t, time.time())

    # Now respond to user input.

    # First, mousewheel events.
    for event in pygame.event.get():
      # It's called a "mousebuttondown" event,
      # but it covers movement of the mousewheel too.
      if event.type == pygame.locals.MOUSEBUTTONDOWN:
        if event.button == 5:   # 5 is "mousewheel down"
          ship.decrease_throttle()
        elif event.button == 4: # 4 is "mousewheel up"
          ship.increase_throttle()

    # Next, rotation via the x and z keys.

    # Start each frame with no rotation; only rotate while a key is
    # held down.
    rotation = 0

    pressed = pygame.key.get_pressed()
    if pressed[pygame.locals.K_z]:
      rotation += 1
    if pressed[pygame.locals.K_x]:
      rotation -= 1
    ship.set_rotation(rotation)

    # TODO: Handle rotation with key-down and key-up events instead,
    # and remember rotation rate between frames. Changing rotation
    # rate should use up fuel and it should be possible to get into a
    # can't-stop-rotating situation when fuel runs out.
    
    # Finally: draw everything.
    screen.fill((0, 0, 0)) # blank the screen
    ship.draw(screen)      # draw the ship
    Spark.draw_all(screen) # draw the sparks
    # TODO: update data display (fuel, velocity, altitude, etc)

    # This replaces the previous drawn frame with the current one.
    pygame.display.flip()


if __name__ == '__main__':
  main()
