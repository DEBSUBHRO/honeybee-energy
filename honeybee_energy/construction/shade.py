# coding=utf-8
"""Shade Construction."""
from __future__ import division

from .window import WindowConstruction
from ..material.glazing import EnergyWindowMaterialGlazing
from ..writer import generate_idf_string

from honeybee._lockable import lockable
from honeybee.typing import valid_ep_string, float_in_range


@lockable
class ShadeConstruction(object):
    """Construction for Shade objects.

    Properties:
        name
        solar_reflectance
        visible_reflectance
        is_specular
        is_default
    """

    __slots__ = ('_name', '_solar_reflectance', '_visible_reflectance',
                 '_is_specular', '_locked')

    def __init__(self, name, solar_reflectance=0.2, visible_reflectance=0.2,
                 is_specular=False):
        """Initialize shade construction.

        Args:
            name: Text string for construction name. Must be <= 100 characters.
                Can include spaces but special characters will be stripped out.
            solar_reflectance: A number between 0 and 1 for the solar reflectance
                of the construction.
            visible_reflectance: A number between 0 and 1 for the solar reflectance
                of the construction.
            is_specular: A boolean to note whether the reflection off the shade
                should be diffuse (False) or specular (True). Set to True if the
                construction is representing a neighboring glass facade or a mirror
                material. Default: False.
        """
        self._locked = False  # unlocked by default
        self.name = name
        self.solar_reflectance = solar_reflectance
        self.visible_reflectance = visible_reflectance
        self.is_specular = is_specular

    @property
    def name(self):
        """Get or set the text string for construction name."""
        return self._name

    @name.setter
    def name(self, name):
        self._name = valid_ep_string(name, 'construction name')

    @property
    def solar_reflectance(self):
        """Get or set the solar reflectance of the shade."""
        return self._solar_reflectance

    @solar_reflectance.setter
    def solar_reflectance(self, value):
        self._solar_reflectance = float_in_range(
            value, 0, 1, 'shade construction solar reflectance')

    @property
    def visible_reflectance(self):
        """Get or set the visible reflectance of the shade."""
        return self._visible_reflectance

    @visible_reflectance.setter
    def visible_reflectance(self, value):
        self._visible_reflectance = float_in_range(
            value, 0, 1, 'shade construction visible reflectance')

    @property
    def is_specular(self):
        """Get or set a boolean to note whether the reflection is diffuse or specular."""
        return self._is_specular

    @is_specular.setter
    def is_specular(self, value):
        try:
            self._is_specular = bool(value)
        except TypeError:
            raise TypeError('Expected boolean for ShadeConstruction.is_specular. '
                            'Got {}.'.format(type(value)))

    @property
    def is_default(self):
        """Boolean to note whether all properties follow the EnergyPlus default."""
        return self._solar_reflectance == 0.2 and \
            self._visible_reflectance == 0.2 and not self._is_specular

    def glazing_construction(self):
        """Get a WindowConstruction that EnergyPlus uses for specular reflection.

        Will be None if is_specular is False.
        """
        if not self.is_specular:
            return None
        glz_mat = EnergyWindowMaterialGlazing(
            self.name, solar_transmittance=0, solar_reflectance=self.solar_reflectance,
            visible_transmittance=0, visible_reflectance=self.visible_reflectance)
        return WindowConstruction(self.name, [glz_mat])

    @classmethod
    def from_dict(cls, data):
        """Create a ShadeConstruction from a dictionary.

        Args:
            data: {
                "type": 'ShadeConstruction',
                "name": 'Generic Overhang Construction',
                "solar_reflectance": 0.35,
                "visible_reflectance": 0.35,
                "is_specular": False
                }
        """
        assert data['type'] == 'ShadeConstruction', \
            'Expected ShadeConstruction. Got {}.'.format(data['type'])
        s_ref = data['solar_reflectance'] if 'solar_reflectance' in data else 0.2
        v_ref = data['visible_reflectance'] if 'visible_reflectance' in data else 0.2
        spec = data['is_specular'] if 'is_specular' in data else False
        return cls(data['name'], s_ref, v_ref, spec)

    def to_idf(self, host_shade_name):
        """IDF string for the ShadingProperty:Reflectance of this construction.

        Note that, if is_specular is True, the glazing_construction() method must
        be used to also write the glazing counstruction into the IDF.

        Args:
            host_shade_name: Text string for the name of a Shade object that
                possesses this ShadeConstruction.
        """
        values = [host_shade_name, self.solar_reflectance, self.visible_reflectance]
        if self.is_specular:
            values.extend([1, self.name])
            comments = ('shading surface name', 'solar reflectance',
                        'visible reflectance',
                        'fraction of shading surface that is glazed',
                        'glazing construction name')
        else:
            comments = ('shading surface name', 'solar reflectance',
                        'visible reflectance')
        return generate_idf_string('ShadingProperty:Reflectance', values, comments)

    def to_radiance_solar(self):
        """Honeybee Radiance material with the solar reflectance."""
        return self._to_radiance(self.solar_reflectance)

    def to_radiance_visible(self):
        """Honeybee Radiance material with the visible reflectance."""
        return self._to_radiance(self.visible_reflectance)

    def to_dict(self):
        """Shade construction dictionary representation."""
        base = {'type': 'ShadeConstruction'}
        base['name'] = self.name
        base['solar_reflectance'] = self.solar_reflectance
        base['visible_reflectance'] = self.visible_reflectance
        base['is_specular'] = self.is_specular
        return base

    def duplicate(self):
        """Get a copy of this construction."""
        return self.__copy__()

    def _to_radiance(self, reflectance):
        try:
            from honeybee_radiance.primitive.material.plastic import Plastic
            from honeybee_radiance.primitive.material.mirror import Mirror
        except ImportError as e:
            raise ImportError('honeybee_radiance library must be installed to use '
                              'to_radiance_* methods. {}'.format(e))
        if not self.is_specular:
            return Plastic.from_single_reflectance(self.name, reflectance)
        else:
            return Mirror.from_single_reflectance(self.name, reflectance)

    def __copy__(self):
        return ShadeConstruction(self.name, self._solar_reflectance,
                                 self._visible_reflectance, self._is_specular)

    def __key(self):
        """A tuple based on the object properties, useful for hashing."""
        return (self.name, self._solar_reflectance, self._visible_reflectance,
                self._is_specular)

    def __hash__(self):
        return hash(self.__key())

    def __eq__(self, other):
        return isinstance(other, ShadeConstruction) and self.__key() == other.__key()

    def __ne__(self, other):
        return not self.__eq__(other)

    def ToString(self):
        """Overwrite .NET ToString."""
        return self.__repr__()

    def __repr__(self):
        return 'ShadeConstruction,\n {}'.format(self.name)
