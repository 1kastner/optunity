#! /usr/bin/env python

# Copyright (c) 2014 KU Leuven, ESAT-STADIUS
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
#
# 3. Neither name of copyright holders nor the names of its contributors
# may be used to endorse or promote products derived from this software
# without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE REGENTS OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""Module to take care of registering solvers for use in the main Optunity API.

Main classes in this module:

* :class:`Solver`
* :class:`GridSearch`
* :class:`RandomSearch`
* :class:`NelderMead`
* :class:`ParticleSwarm`
* :class:`CMA_ES`
  :class:`CSA`

.. warning::
    :class:`NelderMead` is only available if SciPy_ is available.
    :class:`CMA_ES` require DEAP_.

    .. _SciPy: http://http://www.scipy.org/
    .. _DEAP: https://code.google.com/p/deap/


Bibliographic references for some solvers:

.. [HANSEN2001] Nikolaus Hansen and Andreas Ostermeier. *Completely
    derandomized self-adaptation in evolution  strategies*.
    Evolutionary computation, 9(2):159-195, 2001.

.. [DEAP2012] Felix-Antoine Fortin, Francois-Michel De Rainville, Marc-Andre Gardner,
    Marc Parizeau and Christian Gagne, *DEAP: Evolutionary Algorithms Made Easy*,
    Journal of Machine Learning Research, pp. 2171-2175, no 13, jul 2012.


.. moduleauthor:: Marc Claesen

"""

import itertools
import collections
import abc
import functools
import random
import math
import array
import operator as op

# optunity imports
from . import functions as fun
from .solver_registry import register_solver

_numpy_available = True
try:
    import numpy as np
except ImportError:
    _numpy_available = False

_deap_available = True
try:
    import deap
    import deap.creator
    import deap.base
    import deap.tools
    import deap.cma
    import deap.algorithms
except ImportError:
    _deap_available = False
except TypeError:
    # this can happen because DEAP is in Python 2
    # install needs to take proper care of converting
    # 2 to 3 when necessary
    _deap_available = False

def uniform_in_bounds(bounds):
    """Generates a random uniform sample between ``bounds``.

    :param bounds: the bounds we must adhere to
    :type bounds: dict {"name": [lb ub], ...}
    """
    return map(random.uniform, *zip(*bounds.values()))

# python version-independent metaclass usage
SolverBase = abc.ABCMeta('SolverBase', (object, ), {})

class Solver(SolverBase):
    """Base class of all Optunity solvers.
    """

    @abc.abstractmethod
    def optimize(self, f, maximize=True, pmap=map):
        """Optimizes ``f``.

        :param f: the objective function
        :type f: callable
        :param maximize: do we want to maximizes?
        :type maximize: boolean
        :param pmap: the map() function to use
        :type pmap: callable
        :returns:
            - the arguments which optimize ``f``
            - an optional solver report, can be None

        """
        pass

    def maximize(self, f, pmap=map):
        """Maximizes f.

        :param f: the objective function
        :type f: callable
        :param pmap: the map() function to use
        :type pmap: callable
        :returns:
            - the arguments which optimize ``f``
            - an optional solver report, can be None

        """
        return self.optimize(f, True, pmap=pmap)

    def minimize(self, f, pmap=map):
        """Minimizes ``f``.

        :param f: the objective function
        :type f: callable
        :param pmap: the map() function to use
        :type pmap: callable
        :returns:
            - the arguments which optimize ``f``
            - an optional solver report, can be None

        """
        return self.optimize(f, False, pmap=pmap)


# http://stackoverflow.com/a/13743316
def _copydoc(fromfunc, sep="\n"):
    """
    Decorator: Copy the docstring of `fromfunc`
    """
    def _decorator(func):
        sourcedoc = fromfunc.__doc__
        if func.__doc__ == None:
            func.__doc__ = sourcedoc
        else:
            func.__doc__ = sep.join([sourcedoc, func.__doc__])
        return func
    return _decorator

@register_solver('grid search',
                 'finds optimal parameter values on a predefined grid',
                 ['Retrieves the best parameter tuple on a predefined grid.',
                  ' ',
                  'This function requires the grid to be specified via named arguments:',
                  '- names :: argument names',
                  '- values :: list of grid coordinates to test',
                  ' ',
                  'The solver performs evaluation on the Cartesian product of grid values.',
                  'The number of evaluations is the product of the length of all value vectors.'
                  ])
class GridSearch(Solver):
    """
    Exhaustive search over the Cartesian product of parameter tuples.
    Returns x (the tuple which maximizes f) and its score f(x).

    >>> s = GridSearch(x=[1,2,3], y=[-1,0,1])
    >>> best_pars, _ = s.optimize(lambda x, y: x*y)
    >>> best_pars
    {'y': 1, 'x': 3}

    """

    def __init__(self, **kwargs):
        """Initializes the solver with a tuple indicating parameter values.

        >>> s = GridSearch(x=[1,2], y=[3,4])
        >>> s.parameter_tuples
        {'y': [3, 4], 'x': [1, 2]}

        """
        self._parameter_tuples = kwargs

    @staticmethod
    def suggest_from_box(num_evals, **kwargs):
        return kwargs

    @property
    def parameter_tuples(self):
        """Returns the possible values of every parameter."""
        return self._parameter_tuples

    @_copydoc(Solver.optimize)
    def optimize(self, f, maximize=True, pmap=map):

        best_pars = None
        sortedkeys = sorted(self.parameter_tuples.keys())
        f = fun.static_key_order(sortedkeys)(f)

        if maximize:
            comp = lambda score, best: score > best
        else:
            comp = lambda score, best: score < best

        tuples = list(zip(*itertools.product(*zip(*sorted(self.parameter_tuples.items()))[1])))
        scores = pmap(f, *tuples)

        if maximize:
            comp = max
        else:
            comp = min
        best_idx, _ = comp(enumerate(scores), key=op.itemgetter(1))
        best_pars = op.itemgetter(best_idx)(zip(*tuples))
        return dict([(k, v) for k, v in zip(sortedkeys, best_pars)]), None


@register_solver('random search',
                 'random parameter tuples sampled uniformly within box constraints',
                 ['Tests random parameter tuples sampled uniformly within the box constraints.',
                  ' ',
                  'This function requires the following arguments:',
                  '- num_evals :: number of tuples to test',
                  '- box constraints via keywords: constraints are lists [lb, ub]',
                  ' ',
                  'This solver performs num_evals function evaluations.',
                  ' ',
                  'This solver implements the technique described here:',
                  'Bergstra, James, and Yoshua Bengio. Random search for hyper-parameter optimization. Journal of Machine Learning Research 13 (2012): 281-305.']
                 )
class RandomSearch(Solver):

    def __init__(self, num_evals, **kwargs):
        """Initializes the solver with bounds and a number of allowed evaluations.
        kwargs must be a dictionary of parameter-bound pairs representing the box constraints.
        Bounds are a 2-element list: [lower_bound, upper_bound].

        >>> s = RandomSearch(x=[0, 1], y=[-1, 2], num_evals=50)
        >>> s.bounds
        {'y': [-1, 2], 'x': [0, 1]}
        >>> s.num_evals
        50

        """
        assert all([len(v) == 2 and v[0] <= v[1]
                    for v in kwargs.values()]), 'kwargs.values() are not [lb, ub] pairs'
        self._bounds = kwargs
        self._num_evals = num_evals

    @staticmethod
    def suggest_from_box(num_evals, **kwargs):
        d = dict(kwargs)
        d['num_evals'] = num_evals
        return d

    @property
    def upper(self, par):
        """Returns the upper bound of par."""
        return self._bounds[par][1]

    @property
    def lower(self, par):
        """Returns the lower bound of par."""
        return self._bounds[par][0]

    @property
    def bounds(self):
        """Returns a dictionary containing the box constraints."""
        return self._bounds

    @property
    def num_evals(self):
        """Returns the number of evaluations this solver may do."""
        return self._num_evals

    @_copydoc(Solver.optimize)
    def optimize(self, f, maximize=True, pmap=map):

        def generate_rand_args(len=1):
            return [[random.uniform(bounds[0], bounds[1]) for _ in range(len)]
                    for _, bounds in sorted(self.bounds.items())]

        best_pars = None
        sortedkeys = sorted(self.bounds.keys())
        f = fun.static_key_order(sortedkeys)(f)

        if maximize:
            comp = lambda score, best: score > best
        else:
            comp = lambda score, best: score < best

        tuples = generate_rand_args(self.num_evals)
        scores = pmap(f, *tuples)

        if maximize:
            comp = max
        else:
            comp = min
        best_idx, _ = comp(enumerate(scores), key=op.itemgetter(1))
        best_pars = op.itemgetter(best_idx)(zip(*tuples))
        return dict([(k, v) for k, v in zip(sortedkeys, best_pars)]), None


@register_solver('nelder-mead',
                 'simplex method for unconstrained optimization',
                 ['Simplex method for unconstrained optimization',
                 ' ',
                 'The simplex algorithm is a simple way to optimize a fairly well-behaved function.',
                 'The function is assumed to be convex. If not, this solver may yield poor solutions.',
                 ' ',
                 'This solver requires the following arguments:',
                 '- start :: starting point for the solver (through kwargs)',
                 '- ftol :: accuracy up to which to optimize the function (default 1e-4)'
                 ])
class NelderMead(Solver):
    """
    Performs Nelder-Mead optimization to minimize f.

    >>> s = NelderMead(x=1, y=1, xtol=1e-8) #doctest:+SKIP
    >>> best_pars, _ = s.optimize(lambda x, y: -x**2 - y**2) #doctest:+SKIP
    >>> [math.fabs(best_pars['x']) < 1e-8, math.fabs(best_pars['y']) < 1e-8]  #doctest:+SKIP
    [True, True]

    """

    def __init__(self, ftol=1e-4, max_iter=None, **kwargs):
        """Initializes the solver with a tuple indicating parameter values.

        >>> s = NelderMead(x=1, ftol=2) #doctest:+SKIP
        >>> s.start #doctest:+SKIP
        {'x': 1}
        >>> s.ftol #doctest:+SKIP
        2

        """

        self._start = kwargs
        self._ftol = ftol
        self._max_iter = max_iter
        if max_iter is None:
            self._max_iter = len(kwargs) * 200

    @staticmethod
    def suggest_from_seed(num_evals, **kwargs):
        return kwargs

    @property
    def ftol(self):
        """Returns the tolerance."""
        return self._ftol

    @property
    def max_iter(self):
        """Returns the maximum number of iterations."""
        return self._max_iter

    @property
    def start(self):
        """Returns the starting point."""
        return self._start

    @_copydoc(Solver.optimize)
    def optimize(self, f, maximize=True, pmap=map):
        if maximize:
            f = fun.negated(f)

        sortedkeys = sorted(self.start.keys())
        x0 = [float(self.start[k]) for k in sortedkeys]

        f = fun.static_key_order(sortedkeys)(f)

        def func(x):
            return f(*x)

        xopt = self._solve(func, x0)
        return dict([(k, v) for k, v in zip(sortedkeys, xopt)]), None

    def _solve(self, func, x0):
        def f(x):
            return func(list(x))

        x0 = array.array('f', x0)
        N = len(x0)

        vertices = [x0]
        values = [f(x0)]

        # defaults taken from Wikipedia and SciPy
        alpha = 1.; gamma = 2.; rho = -0.5; sigma = 0.5;
        one2np1 = range(1,N+1)
        nonzdelt = 0.05
        zdelt = 0.00025

        # generate vertices
        for k in range(N):
            vert = vertices[0][:]
            if vert[k] != 0:
                vert[k] = (1 + nonzdelt) * vert[k]
            else:
                vert[k] = zdelt

            vertices.append(vert)
            values.append(f(vert))

        niter = 1
        while niter < self.max_iter:

            # sort vertices by ftion value
            vertices, values = NelderMead.sort_vertices(vertices, values)

            # check for convergence
            if abs(values[0] - values[-1]) <= self.ftol:
                break

            niter += 1

            # compute center of gravity
            x0 = NelderMead.simplex_center(vertices[:-1])

            # reflect
            xr = NelderMead.reflect(x0, vertices[-1], alpha)
            fxr = f(xr)
            if vertices[0] < fxr < vertices[-2]:
                vertices[-1] = xr
                values[-1] = fxr
                continue

            # expand
            if fxr < values[0]:
                xe = NelderMead.reflect(x0, vertices[-1], gamma)
                fxe = f(xe)
                if fxe < fxr:
                    vertices[-1] = xe
                    values[-1] = fxe
                else:
                    vertices[-1] = xr
                    values[-1] = fxr
                continue

            # contract
            xc = NelderMead.reflect(x0, vertices[-1], rho)
            fxc = f(xc)
            if fxc < values[-1]:
                vertices[-1] = xc
                values[-1] = fxc
                continue

            # reduce
            for idx in range(1, len(vertices)):
                vertices[idx] = NelderMead.reflect(vertices[0], vertices[idx],
                                                   sigma)
                values[idx] = f(vertices[idx])

        return list(vertices[min(enumerate(values), key=op.itemgetter(1))[0]])

    @staticmethod
    def simplex_center(vertices):
        vector_sum = map(sum, zip(*vertices))
        return array.array('f', map(lambda x: x / len(vertices), vector_sum))

    @staticmethod
    def sort_vertices(vertices, values):
        sort_idx, values = zip(*sorted(enumerate(values), key=op.itemgetter(1)))
        vertices = map(lambda x: vertices[x], sort_idx)
        return list(vertices), list(values)

    @staticmethod
    def scale(vertex, coeff):
        return array.array('f', map(lambda x: coeff * x, vertex))

    @staticmethod
    def reflect(x0, xn1, alpha):
        diff = map(op.sub, x0, xn1)
        xr = array.array('f', map(op.add, x0, NelderMead.scale(diff, alpha)))
        return xr


class CMA_ES(Solver):
    """
    Covariance Matrix Adaptation Evolutionary Strategy

    This solver implements the technique described in [HANSEN2001]_.
    This solver uses an implementation available in the DEAP library [DEAP2012]_.

    """

    def __init__(self, num_generations, sigma=1.0, Lambda=None, **kwargs):
        """blah"""
        if not _deap_available:
            raise ImportError('This solver requires DEAP but it is missing.')
        if not _numpy_available:
            raise ImportError('This solver requires NumPy but it is missing.')

        self._num_generations = num_generations
        self._start = kwargs
        self._sigma = sigma
        self._lambda = Lambda

    @staticmethod
    def suggest_from_seed(num_evals, **kwargs):
        fertility = 4 + 3 * math.log(len(kwargs))
        d = dict(kwargs)
        d['num_generations'] = int(math.ceil(float(num_evals) / fertility))
        # num_gen is overestimated
        # this will require slightly more function evaluations than permitted by num_evals
        return d

    @property
    def num_generations(self):
        return self._num_generations

    @property
    def start(self):
        """Returns the starting point for CMA-ES."""
        return self._start

    @property
    def lambda_(self):
        return self._lambda

    @property
    def sigma(self):
        return self._sigma

    @_copydoc(Solver.optimize)
    def optimize(self, f, maximize=True, pmap=map):
        toolbox = deap.base.Toolbox()
        if maximize:
            fit = 1.0
        else:
            fit = -1.0
        deap.creator.create("FitnessMax", deap.base.Fitness,
                            weights=(fit,))
        Fit = deap.creator.FitnessMax
        deap.creator.create("Individual", list,
                            fitness=Fit)
        Individual = deap.creator.Individual

        if self.lambda_:
            strategy = deap.cma.Strategy(centroid=self.start.values(),
                                            sigma=self.sigma, lambda_=self.lambda_)
        else:
            strategy = deap.cma.Strategy(centroid=self.start.values(),
                                            sigma=self.sigma)
        toolbox.register("generate", strategy.generate, Individual)
        toolbox.register("update", strategy.update)

        @functools.wraps(f)
        def evaluate(individual):
            return (f(**dict([(k, v)
                                for k, v in zip(self.start.keys(),
                                                individual)])),)
        toolbox.register("evaluate", evaluate)
        toolbox.register("map", pmap)

        hof = deap.tools.HallOfFame(1)
        deap.algorithms.eaGenerateUpdate(toolbox=toolbox,
                                            ngen=self._num_generations,
                                            halloffame=hof, verbose=False)

        return dict([(k, v)
                        for k, v in zip(self.start.keys(), hof[0])]), None

# CMA_ES solver requires deap > 1.0.1
# http://deap.readthedocs.org/en/latest/examples/cmaes.html
if _deap_available and _numpy_available:
    CMA_ES =register_solver('cma-es', 'covariance matrix adaptation evolutionary strategy',
                        ['CMA-ES: covariance matrix adaptation evolutionary strategy',
                        ' ',
                        'This method requires the following parameters:',
                        '- num_generations :: number of generations to use',
                        '- sigma :: (optional) initial covariance, default 1',
                        '- Lambda :: (optional) measure of reproducibility',
                        '- starting point: through kwargs'
                        ' ',
                        'This method is described in detail in:',
                        'Hansen and Ostermeier, 2001. Completely Derandomized Self-Adaptation in Evolution Strategies. Evolutionary Computation'
                         ])(CMA_ES)


# this implementation of the PSO solver has been replaced
class ParticleSwarmDEAP(Solver):
    """
    This solver uses an implementation available in the DEAP library [DEAP2012]_.

    """

    def __init__(self, num_particles, num_generations, max_speed=None, **kwargs):
        """blah"""
        if not _deap_available:
            raise ImportError('This solver requires DEAP but it is missing.')

        assert all([len(v) == 2 and v[0] <= v[1]
                    for v in kwargs.values()]), 'kwargs.values() are not [lb, ub] pairs'
        self._bounds = kwargs
        self._ttype = collections.namedtuple('ttype', kwargs.keys())
        self._num_particles = num_particles
        self._num_generations = num_generations

        if max_speed is None:
            max_speed = 2.0/num_generations
        self._max_speed = max_speed
        self._smax = [self.max_speed * (b[1] - b[0])
                        for _, b in self.bounds.items()]
        self._smin = map(op.neg, self.smax)

        self._toolbox = deap.base.Toolbox()
        self._toolbox.register("particle", self.generate)
        self._toolbox.register("population", deap.tools.initRepeat, list,
                                self.toolbox.particle)
        self._toolbox.register("update", self.updateParticle,
                                phi1=2.0, phi2=2.0)

    @staticmethod
    def suggest_from_box(num_evals, **kwargs):
        d = dict(kwargs)
        if num_evals > 200:
            d['num_particles'] = 50
            d['num_generations'] = int(math.ceil(float(num_evals) / 50))
        elif num_evals > 10:
            d['num_particles'] = 10
            d['num_generations'] = int(math.ceil(float(num_evals) / 10))
        else:
            d['num_particles'] = num_evals
            d['num_generations'] = 1
        return d

    @property
    def num_particles(self):
        return self._num_particles

    @property
    def num_generations(self):
        return self._num_generations

    @property
    def toolbox(self):
        return self._toolbox

    @property
    def max_speed(self):
        return self._max_speed

    @property
    def smax(self):
        return self._smax

    @property
    def smin(self):
        return self._smin

    @property
    def bounds(self):
        return self._bounds

    @property
    def ttype(self):
        return self._ttype

    def generate(self):
        part = self._Particle(random.uniform(bounds[0], bounds[1])
                                        for _, bounds in self.bounds.items())
        part.speed = [random.uniform(smin, smax)
                        for smin, smax in zip(self.smin, self.smax)]
        return part

    def updateParticle(self, part, best, phi1, phi2):
        u1 = (random.uniform(0, phi1) for _ in range(len(part)))
        u2 = (random.uniform(0, phi2) for _ in range(len(part)))
        v_u1 = map(op.mul, u1,
                    map(op.sub, part.best, part))
        v_u2 = map(op.mul, u2,
                    map(op.sub, best, part))
        part.speed = list(map(op.add, part.speed,
                                map(op.add, v_u1, v_u2)))
        for i, speed in enumerate(part.speed):
            if speed < self.smin[i]:
                part.speed[i] = self.smin[i]
            elif speed > self.smax[i]:
                part.speed[i] = self.smax[i]
        part[:] = list(map(op.add, part, part.speed))

    @_copydoc(Solver.optimize)
    def optimize(self, f, maximize=True, pmap=map):

        @functools.wraps(f)
        def evaluate(individual):
            return (f(**dict([(k, v)
                              for k, v in zip(self.bounds.keys(),
                                              individual)])),)

        self._toolbox.register("evaluate", evaluate)
        self._toolbox.register("map", pmap)

        if maximize:
            fit = 1.0
        else:
            fit = -1.0
        deap.creator.create("FitnessMax", deap.base.Fitness,
                            weights=(fit,))
        FitnessMax = deap.creator.FitnessMax

        deap.creator.create("Particle", list,
                            fitness=FitnessMax, speed=list,
                            best=None)
        self._Particle = deap.creator.Particle

        pop = self.toolbox.population(self.num_particles)
        best = None

        for g in range(self.num_generations):
            fitnesses = self.toolbox.map(self.toolbox.evaluate, pop)
            for part, fitness in zip(pop, fitnesses):
                part.fitness.values = fitness
                if not part.best or part.best.fitness < part.fitness:
                    part.best = self._Particle(part)
                    part.best.fitness.values = part.fitness.values
                if not best or best.fitness < part.fitness:
                    best = self._Particle(part)
                    best.fitness.values = part.fitness.values
            for part in pop:
                self.toolbox.update(part, best)

        return dict([(k, v)
                        for k, v in zip(self.bounds.keys(), best)]), None

@register_solver('particle swarm',
                 'particle swarm optimization',
                 ['Maximizes the function using particle swarm optimization.',
                  ' ',
                  'This is a two-phase approach:',
                  '1. Initialization: randomly initializes num_particles particles.',
                  '   Particles are randomized uniformly within the box constraints.',
                  '2. Iteration: particles move during num_generations iterations.',
                  '   Movement is based on their velocities and mutual attractions.',
                  ' ',
                  'This function requires the following arguments:',
                  '- num_particles: number of particles to use in the swarm',
                  '- num_generations: number of iterations used by the swarm',
                  '- max_speed: maximum speed of the particles in each direction (in (0, 1])',
                  '- box constraints via key words: constraints are lists [lb, ub]', ' ',
                  'This solver performs num_particles*num_generations function evaluations.'
                  ])
class ParticleSwarm(Solver):
    """
    TODO
    """

    class Particle:
        def __init__(self, position, speed, best, fitness, best_fitness):
            """Constructs a Particle."""
            self.position = position
            self.speed = speed
            self.best = best
            self.fitness = fitness
            self.best_fitness = best_fitness

        def clone(self):
            """Clones this Particle."""
            return ParticleSwarm.Particle(position=self.position[:], speed=self.speed[:],
                                          best=self.best[:], fitness=self.fitness,
                                          best_fitness=self.best_fitness)

        def __str__(self):
            string = 'Particle{position=' + str(self.position)
            string += ', speed=' + str(self.speed)
            string += ', best=' + str(self.best)
            string += ', fitness=' + str(self.fitness)
            string += ', best_fitness=' + str(self.best_fitness)
            string += '}'
            return string

    def __init__(self, num_particles, num_generations, max_speed=None, **kwargs):
        """blah"""

        assert all([len(v) == 2 and v[0] <= v[1]
                    for v in kwargs.values()]), 'kwargs.values() are not [lb, ub] pairs'
        self._bounds = kwargs
        self._ttype = collections.namedtuple('ttype', kwargs.keys())
        self._num_particles = num_particles
        self._num_generations = num_generations

        if max_speed is None:
            max_speed = 2.0/num_generations
        self._max_speed = max_speed
        self._smax = [self.max_speed * (b[1] - b[0])
                        for _, b in self.bounds.items()]
        self._smin = map(op.neg, self.smax)

        self._phi1 = 2.0
        self._phi2 = 2.0

    @property
    def phi1(self):
        return self._phi1

    @property
    def phi2(self):
        return self._phi2

    @staticmethod
    def suggest_from_box(num_evals, **kwargs):
        d = dict(kwargs)
        if num_evals > 200:
            d['num_particles'] = 50
            d['num_generations'] = int(math.ceil(float(num_evals) / 50))
        elif num_evals > 10:
            d['num_particles'] = 10
            d['num_generations'] = int(math.ceil(float(num_evals) / 10))
        else:
            d['num_particles'] = num_evals
            d['num_generations'] = 1
        return d

    @property
    def num_particles(self):
        return self._num_particles

    @property
    def num_generations(self):
        return self._num_generations

    @property
    def max_speed(self):
        return self._max_speed

    @property
    def smax(self):
        return self._smax

    @property
    def smin(self):
        return self._smin

    @property
    def bounds(self):
        return self._bounds

    @property
    def ttype(self):
        return self._ttype

    def generate(self):
        part = ParticleSwarm.Particle(position=array.array('d', uniform_in_bounds(self.bounds)),
                                      speed=array.array('d', map(random.uniform,
                                                                 self.smin, self.smax)),
                                      best=None, fitness=None, best_fitness=None)
        return part

    def updateParticle(self, part, best, phi1, phi2):
        u1 = (random.uniform(0, phi1) for _ in range(len(part.position)))
        u2 = (random.uniform(0, phi2) for _ in range(len(part.position)))
        v_u1 = map(op.mul, u1,
                    map(op.sub, part.best, part.position))
        v_u2 = map(op.mul, u2,
                    map(op.sub, best.position, part.position))
        part.speed = array.array('d', map(op.add, part.speed,
                                          map(op.add, v_u1, v_u2)))
        for i, speed in enumerate(part.speed):
            if speed < self.smin[i]:
                part.speed[i] = self.smin[i]
            elif speed > self.smax[i]:
                part.speed[i] = self.smax[i]
        part.position[:] = array.array('d', map(op.add, part.position, part.speed))

    @_copydoc(Solver.optimize)
    def optimize(self, f, maximize=True, pmap=map):

        @functools.wraps(f)
        def evaluate(particle):
            return f(**dict([(k, v)
                              for k, v in zip(self.bounds.keys(),
                                              particle.position)]))

        if maximize:
            fit = 1.0
        else:
            fit = -1.0

        pop = [self.generate() for _ in range(self.num_particles)]
        best = None

        for g in range(self.num_generations):
            fitnesses = pmap(evaluate, pop)
            for part, fitness in zip(pop, fitnesses):
                part.fitness = fit*fitness
                if not part.best or part.best_fitness < part.fitness:
                    part.best = part.position
                    part.best_fitness = part.fitness
                if not best or best.fitness < part.fitness:
                    best = part.clone()
            for part in pop:
                self.updateParticle(part, best, self.phi1, self.phi2)

        return dict([(k, v)
                        for k, v in zip(self.bounds.keys(), best.position)]), None

@register_solver('annealing',
                 'coupled simulated annealing',
                 ['TODO'])
class CSA(Solver):
    """
    TODO

    Based on ftp://ftp.esat.kuleuven.be/pub/SISTA/sdesouza/papers/CSA2009accepted.pdf
    """

    class SA:
        """Class to model a single simulated annealing process."""

        def __init__(self, x0):
            self._x = x0[:]
            self._y = x0[:]
            self._cost = None
            self._ycost = None
            self._log = []

        @property
        def log(self):
            """Returns a log of all solutions this process has been in.

            This is returned as a list of (solution, cost)-tuples."""
            return self._log

        @property
        def T(self):
            return self._T

        @property
        def Tacc(self):
            return self._Tacc

        @property
        def k(self):
            return self._k

        @property
        def maxk(self):
            return self._maxk

        @property
        def y(self):
            return self._y

        @property
        def ycost(self):
            return self._ycost

        @ycost.setter
        def ycost(self, value):
            self._ycost = value

        @property
        def x(self):
            return self._x

        @x.setter
        def x(self, value):
            self._x = value[:]

        @property
        def cost(self):
            return self._cost

        def generate(self, gk, Tk):
            """Generate a random probe solution."""
            eps = gk(Tk)
            self._y = map(op.add, self.x, eps)

        def accept(self, accept_probability):
            # update the log of this SA process
            self._log.append((self.y[:], self.ycost))

            # accept if required
            if random.uniform(0, 1) <= accept_probability:
                self.x = self.y
                self._cost = self.ycost
                self._y = None
                self._ycost = None
            else:
                self._y = None
                self._ycost = None

    def __init__(self, num_processes, num_generations, T_0, Tacc_0, **kwargs):
        """blah"""
        assert all([len(v) == 2 and v[0] <= v[1]
                    for v in kwargs.values()]), 'kwargs.values() are not [lb, ub] pairs'
        self._bounds = kwargs
        self._num_dimensions = len(kwargs)
        self._num_processes = num_processes
        self._num_generations = num_generations
        self._T_0 = T_0
        self._Tacc_0 = Tacc_0

    def g(self, Tk):
        return [Tk * CSA.cauchy_sample() for _ in range(self.num_dimensions)]

    @property
    def num_dimensions(self):
        return self._num_dimensions

    @property
    def num_processes(self):
        return self._num_processes

    @property
    def num_generations(self):
        return self._num_generations

    def T(self, k=0):
        return self._T_0 / (k + 1)

    def Tacc(self, k=0):
        if k:
            return self._Tacc_0 / math.log(k + 1)
        else:
            return self._Tacc_0

    def exp(self, cost, multiplier, k):
        return math.exp(-cost * multiplier / self.Tacc(k))

    @staticmethod
    def suggest_from_box(num_evals, **kwargs):
        d = dict(kwargs)
        if num_evals > 200:
            d['num_processes'] = 50
            d['num_generations'] = int(math.ceil(float(num_evals) / 50))
        elif num_evals > 10:
            d['num_processes'] = 10
            d['num_generations'] = int(math.ceil(float(num_evals) / 10))
        else:
            d['num_processes'] = num_evals
            d['num_generations'] = 1
        return d

    @staticmethod
    def cauchy_sample():
        return math.tan(math.pi * (random.uniform(0, 1) - 0.5))

    @property
    def bounds(self):
        return self._bounds

    @_copydoc(Solver.optimize)
    def optimize(self, f, maximize=True, pmap=map):
        if maximize:
            mult = -1.0
            comp = op.gt
        else:
            mult = 1.0
            comp = op.lt

        def evaluate(state):
            print('state: ' + str(state))
            return f(**dict([(k, v)
                              for k, v in zip(self.bounds.keys(),
                                              state)]))

        # initialization
        processes = [CSA.SA(uniform_in_bounds(self.bounds))
                     for _ in range(self.num_processes)]

        states = [p.y for p in processes]
        costs = pmap(evaluate, states)

        for process, cost in zip(processes, costs):
            process.ycost = cost
            process.accept(1.0)

        # start of annealing iterations
        for iteration in range(self.num_generations - 1):

            k = float(iteration)
            for process in processes:
                process.generate(self.g, self.T(k))

            states = [p.y for p in processes]
            costs = pmap(evaluate, states)

            gamma = reduce(op.add, [self.exp(proc.cost, mult, k)
                                    for proc in processes])

            print('gamma: ' + str(gamma))
            for process, ycost in zip(processes, costs):
                process.ycost = ycost
                if comp(process.ycost, process.cost):
                    accept_probability = 1.0
                else:
                    expcost = self.exp(ycost, mult, k)
                    accept_probability = expcost / (expcost + gamma)
                print('cost: ' + str(process.cost) + ' ycost: ' + str(process.ycost) + ' prob: ' + str(accept_probability))
                process.accept(accept_probability)

        logs = itertools.chain(*[p.log for p in processes])
        if maximize:
            best = max(logs, key=op.itemgetter(1))[0]
        else:
            best = min(logs, key=op.itemgetter(1))[0]

        return dict([(k, v)
                        for k, v in zip(self.bounds.keys(), best)]), None
