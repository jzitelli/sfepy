r"""
Incompressible Mooney-Rivlin hyperelastic material model.
In this model, the deformation energy density per unit reference volume is
given by

.. math::
    W = C_{(10)} \, \left( \overline I_1 - 3 \right)
        + C_{(01)} \, \left( \overline I_2 - 3 \right) \;,

where :math:`\overline I_1` and :math:`\overline I_2` are the first
and second main invariants of the deviatoric part of the right
Cauchy-Green deformation tensor :math:`\overline{\bf C}`. The coefficients
:math:`C_{(10)}` and :math:`C_{(01)}` are material parameters.

Components of the second Piola-Kirchhoff stress are in the case of an
incompressible material

.. math::
    S_{ij} = 2 \, \pdiff{W}{C_{ij}} - p \, F^{-1}_{ik} \, F^{-T}_{kj} \;,

where :math:`p` is the hydrostatic pressure.

Large deformation is described using the total Lagrangian formulation in this
example. Incompressibility is treated by mixed displacement-pressure
formulation. The weak formulation is:
Find the displacement field :math:`\ul{u}` and pressure field :math:`p`
such that:

.. math::
    \intl{\Omega\suz}{} \ull{S}\eff(\ul{u}, p) : \ull{E}(\ul{v})
    \difd{V} = 0
    \;, \quad \forall \ul{v} \;,

    \intl{\Omega\suz}{} q\, (J(\ul{u})-1) \difd{V} = 0
    \;, \quad \forall q \;.

Following formula holds for axial true (Cauchy) stress in the case of uniaxial
stress:

.. math::
    \sigma(\lambda) =
        2\, \left( C_{(10)} + \frac{C_{(01)}}{\lambda} \right) \,
        \left( \lambda^2 - \frac{1}{\lambda} \right) \;,

where :math:`\lambda = l/l_0` is the prescribed stretch (:math:`l_0` and
:math:`l` being the original and deformed specimen length respectively).

The boundary conditions are set so that a state of uniaxial stress is achieved,
i.e. appropriate components of displacement are fixed on the "Left", "Bottom",
and "Near" faces and monotonously increasing displacement is prescribed on the
"Right" face. This prescribed displacement is then used to calculate
:math:`\lambda` and to convert second Piola-Kirchhoff stress to true (Cauchy)
stress.

**Note**

The relationship between material parameters used in the *SfePy* hyperelastic
terms (:class:`NeoHookeanTLTerm <sfepy.terms.terms_hyperelastic_tl.NeoHookeanTLTerm>`,
:class:`MooneyRivlinTLTerm <sfepy.terms.terms_hyperelastic_tl.MooneyRivlinTLTerm>`)
and the ones used in this example is:

.. math::
    \mu = 2\, C_{(10)} \;,

    \kappa = 2\, C_{(01)} \;.

**Usage Examples**

Default options::

  $ python examples/large_deformation/hyperelastic_tl_up_interactive.py

To show a comparison of stress against the analytic formula::

  $ python examples/large_deformation/hyperelastic_tl_up_interactive.py -p

Using different mesh fineness::

  $ python examples/large_deformation/hyperelastic_tl_up_interactive.py --shape 5 5 5

Different dimensions of the computational domain::

  $ python examples/large_deformation/hyperelastic_tl_up_interactive.py --dims 2 1 3

Different length of time interval and/or number of time steps::

  $ python examples/large_deformation/hyperelastic_tl_up_interactive.py -t 0,15,21
"""
from __future__ import print_function, absolute_import
import argparse
import sys

SFEPY_DIR = '.'
sys.path.append(SFEPY_DIR)

import matplotlib.pyplot as plt
import numpy as np

from sfepy.base.base import IndexedStruct, Struct
from sfepy.discrete import (
    FieldVariable, Material, Integral, Function, Equation, Equations, Problem)
from sfepy.discrete.conditions import Conditions, EssentialBC
from sfepy.discrete.fem import FEDomain, Field
from sfepy.homogenization.utils import define_box_regions
from sfepy.mesh.mesh_generators import gen_block_mesh
from sfepy.solvers.ls import ScipyDirect
from sfepy.solvers.nls import Newton
from sfepy.solvers.ts_solvers import SimpleTimeSteppingSolver
from sfepy.terms import Term

DIMENSION = 3

# Material parameters:
C10 = 20.
C01 = 10.

def get_displacement(ts, coors, bc=None, problem=None):
    """
    Define time-dependent displacement
    """
    out = 1. * ts.time * coors[:, 0]
    return out

def plot_graphs(undeformed_lenght=1.0):
    stretch = 1 + np.array(global_displacement) / undeformed_lenght

    # axial stress values
    stress_fem_2pk = np.array([sig for sig in global_stress])
    stress_fem = stress_fem_2pk * stretch**2
    stress_analytic = 2 * (C10 + C01/stretch) * (stretch**2 - 1./stretch)

    fig = plt.figure()
    ax_stress = fig.add_subplot(211)
    ax_difference = fig.add_subplot(212)

    ax_stress.plot(stretch, stress_fem, '.-', label='FEM')
    ax_stress.plot(stretch, stress_analytic, '--', label='analytic')

    ax_difference.plot(stretch, stress_fem - stress_analytic, '.-')

    ax_stress.legend(loc='best').draggable()
    ax_stress.set_ylabel(r'true stress $\mathrm{[Pa]}$')
    ax_stress.grid()

    ax_difference.set_ylabel(r'difference in true stress $\mathrm{[Pa]}$')
    ax_difference.set_xlabel(r'stretch $\mathrm{[-]}$')
    ax_difference.grid()
    plt.show()

global_stress = []
global_displacement = []

def stress_strain(out, problem, _state, order=1, **_):
    strain = problem.evaluate(
        'dw_tl_he_neohook.%d.Omega(m.mu, v, u)' % (2*order),
        mode='el_avg', term_mode='strain', copy_materials=False)

    out['green_strain'] = Struct(
        name='output_data', mode='cell', data=strain, dofs=None)

    stress_10 = problem.evaluate(
        'dw_tl_he_neohook.%d.Omega(m.mu, v, u)' % (2*order),
        mode='el_avg', term_mode='stress', copy_materials=False)
    stress_01 = problem.evaluate(
        'dw_tl_he_mooney_rivlin.%d.Omega(m.kappa, v, u)' % (2*order),
        mode='el_avg', term_mode='stress', copy_materials=False)
    stress_p = problem.evaluate(
        'dw_tl_bulk_pressure.%d.Omega(v, u, p)' % (2*order),
        mode='el_avg', term_mode='stress', copy_materials=False)
    stress = stress_10 + stress_01 + stress_p

    out['stress'] = Struct(
        name='output_data', mode='cell', data=stress, dofs=None)

    global_stress.append(stress[0, 0, 0, 0])
    global_displacement.append(np.max(out['u'].data[:, 0]))

    return out

def main(dims=None, shape=None, centre=None, order=1, ts=None, do_plot=True):
    if dims is None: dims = [1.0, 1.0, 1.0]
    if shape is None: shape = [4, 4, 4]
    if centre is None: centre = [0.5*dim for dim in dims]
    if ts is None: ts = {'t0' : 0.0, 't1' : 10.0, 'n_steps' : 11}

    ### Mesh and regions ###
    mesh = gen_block_mesh(
        dims, shape, centre, name='block', verbose=False)
    domain = FEDomain('domain', mesh)

    omega = domain.create_region('Omega', 'all')

    lbn, rtf = domain.get_mesh_bounding_box()
    box_regions = define_box_regions(3, lbn, rtf)
    regions = dict([
        [r, domain.create_region(r, box_regions[r][0], box_regions[r][1])]
        for r in box_regions])

    ### Fields ###
    scalar_field = Field.from_args(
        'fu', np.float64, 'scalar', omega, approx_order=order-1)
    vector_field = Field.from_args(
        'fv', np.float64, 'vector', omega, approx_order=order)

    u = FieldVariable('u', 'unknown', vector_field, history=1)
    v = FieldVariable('v', 'test', vector_field, primary_var_name='u')
    p = FieldVariable('p', 'unknown', scalar_field, history=1)
    q = FieldVariable('q', 'test', scalar_field, primary_var_name='p')

    ### Material ###
    m = Material(
        'm', mu=2*C10, kappa=2*C01,
    )

    ### Boundary conditions ###
    x_sym = EssentialBC('x_sym', regions['Left'], {'u.0' : 0.0})
    y_sym = EssentialBC('y_sym', regions['Near'], {'u.1' : 0.0})
    z_sym = EssentialBC('z_sym', regions['Bottom'], {'u.2' : 0.0})
    disp_fun = Function('disp_fun', get_displacement)
    displacement = EssentialBC('displacement', regions['Right'], {'u.0' : disp_fun})
    ebcs = Conditions([x_sym, y_sym, z_sym, displacement])

    ### Terms and equations ###
    integral = Integral('i', order=2*order)

    term_neohook = Term.new(
        'dw_tl_he_neohook(m.mu, v, u)',
        integral, omega, m=m, v=v, u=u)
    term_mooney = Term.new(
        'dw_tl_he_mooney_rivlin(m.kappa, v, u)',
        integral, omega, m=m, v=v, u=u)
    term_pressure = Term.new(
        'dw_tl_bulk_pressure(v, u, p)',
        integral, omega, v=v, u=u, p=p)

    term_volume_change = Term.new(
        'dw_tl_volume(q, u)',
        integral, omega, q=q, u=u, term_mode='volume')
    term_volume = Term.new(
        'dw_volume_integrate(q)',
        integral, omega, q=q)

    eq_balance = Equation('balance', term_neohook+term_mooney+term_pressure)
    eq_volume = Equation('volume', term_volume_change-term_volume)
    equations = Equations([eq_balance, eq_volume])

    ### Solvers ###
    ls = ScipyDirect({})
    nls_status = IndexedStruct()
    nls = Newton(
        {'is_linear' : False},
        lin_solver=ls, status=nls_status
    )

    ### Problem ###
    pb = Problem(
        'hyper', equations=equations, nls=nls, ls=ls,
    )
    pb.set_bcs(ebcs=ebcs)
    pb.set_ics(ics=Conditions([]))

    tss = SimpleTimeSteppingSolver(ts, problem=pb)
    tss.init_time()

    ### Solution ###
    def stress_strain_fun(*args, **kwargs):
        return stress_strain(*args, order=order, **kwargs)

    for step, time, state in tss(
            save_results=True, post_process_hook=stress_strain_fun):
        pass

    if do_plot:
        plot_graphs(undeformed_lenght=dims[0])

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--order', type=int, default=1,
        help='Approximation order of displacements [default: %(default)s]')
    parser.add_argument(
        '--dims', metavar=('DIM_X', 'DIM_Y', 'DIM_Z'), action='store',
        dest='dims', type=float, nargs=DIMENSION, default=[1.0, 1.0, 1.0],
        help='dimensions of the block [default: %(default)s]')
    parser.add_argument(
        '--shape', metavar=('SHAPE_X', 'SHAPE_Y', 'SHAPE_Z'), action='store',
        dest='shape', type=int, nargs=DIMENSION, default=[4, 4, 4],
        help='shape (counts of nodes in x, y, z) of the block [default: '
        '%(default)s]')
    parser.add_argument(
        '--centre', metavar=('CENTRE_X', 'CENTRE_Y', 'CENTRE_Z'),
        action='store', dest='centre', type=float, nargs=DIMENSION,
        default=[0.5, 0.5, 0.5],
        help='centre of the block [default: %(default)s]')
    parser.add_argument(
        '-p', '--plot', action='store_true', default=False,
        help='Whether to plot a comparison with analytical formula.')
    parser.add_argument(
        '-t', '--ts',
        type=str, default='0.0,10.0,11',
        help='Start time, end time, and number of time steps [default: '
        '"%(default)s"]')
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()
    ts_vals = args.ts.split(',')
    ts_dict = {
        't0' : float(ts_vals[0]), 't1' : float(ts_vals[1]),
        'n_step' : int(ts_vals[2])}
    main(
        dims=args.dims, shape=args.shape, centre=args.centre, order=args.order,
        ts=ts_dict, do_plot=args.plot,
    )
