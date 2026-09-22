"""The methods scored on the eye's input: what each one computes, and the readout they share.

A method takes a rendered clip (contract 1) and returns, per frame and per column, a distance in metres or
an explicit unknown, and where it claims one, a moving-object share. Everything is scored in the lattice
space, so a method that consumes more than the 721 luminances the eye receives says so and is reported as
an upper bound (`conectoma/methods/readout.py`, and wip dossier 09 in the management repo).
"""
