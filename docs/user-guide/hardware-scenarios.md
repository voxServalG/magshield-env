# Define Hardware, External Field, and Pose

Hardware and scenario data turn a response model into an executable control
environment. Declare them in SI units and preserve the same channel and point
identities used by the physics source.

## Hardware

For every channel declare lower and upper current in amperes, positive slew
rate in amperes per second, resistance in ohms, and positive voltage limit in
volts. Declare the controller timestep in seconds. Channel identifiers must be
unique and appear in exactly the response-column order.

At each step, current bounds, slew bounds, and the voltage-derived bound jointly
define the legal current increment. Illegal actions follow the explicitly
selected behavior: `project_and_report` exposes both requested and applied
actions plus constraint evidence, while `terminate` ends the episode. Neither
mode silently clips without evidence.

## Static external field and pose

A static scenario may supply one external field over the point set and an
optional pose. Pose is complete only when translation `(x,y,z)` in metres and a
quaternion `(x,y,z,w)` are both present. The quaternion expresses orientation;
it is not interchangeable with Euler angles.

Declare the external field's vector-component frame explicitly. Fixed response
packages require it to equal the response frame. Dynamic geometry treats each
pose as a transform from the point-set frame to the conductor-path frame, then
evaluates the response and external-field components in that target frame.

## Trajectories

An HDF5 trajectory binds external field frames, timestamps or frame order, and
optional pose arrays. Translation and quaternion datasets must be both present
or both absent. All time-varying arrays must share their leading frame count.
The trajectory file declares field unit `T`, external-field component frame,
pose translation unit `m`, and quaternion order `xyzw`; names alone are not
accepted as unit evidence.
For dynamic geometry, every runtime frame needs a pose so the conductor
response can be recomputed. A repeated exact pose may use the identity-bound
cache; an unseen pose is evaluated directly.

## Reinforcement-learning interface

Choose full-field observations or a declared linear basis projection. Basis
mode requires an explicit basis source and the basis vector-component frame,
which must equal the response frame. Reward scales, thresholds, and weights
for field error, power, current change, constraints, and optional nominal
current deviation are physical declarations, not hidden defaults to tune after
the fact.

Use current `--help` output for command syntax and examples.
