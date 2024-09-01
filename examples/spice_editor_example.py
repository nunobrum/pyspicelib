from spicelib import SpiceEditor
from spicelib.simulators.ltspice_simulator import LTspice

LTspice.create_netlist("./testfiles/Noise.asc")
se = SpiceEditor("./testfiles/Noise.net")

# Object Oriented Approach
se['R1'].value = 11000
se['C1'].value = 1.1E-6
se['V1'].value = 11

# Legacy Approach
se.set_component_value('R1', 11000)
se.set_component_value('C1', 1.1E-6)
se.set_component_value('V1', 11)

se.run(run_filename="./testfiles/Noise_1.net", timeout=10, simulator=LTspice)
