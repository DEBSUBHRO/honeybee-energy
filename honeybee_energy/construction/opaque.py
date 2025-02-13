# coding=utf-8
"""Opaque Construction."""
from __future__ import division

from ._base import _ConstructionBase
from ..material._base import _EnergyMaterialOpaqueBase
from ..material.opaque import EnergyMaterial, EnergyMaterialNoMass
from ..reader import parse_idf_string

from honeybee._lockable import lockable

import re
import os


@lockable
class OpaqueConstruction(_ConstructionBase):
    """Opaque energy construction.

    Properties:
        * name
        * materials
        * layers
        * unique_materials
        * r_value
        * u_value
        * u_factor
        * r_factor
        * inside_emissivity
        * inside_solar_reflectance
        * inside_visible_reflectance
        * outside_emissivity
        * outside_solar_reflectance
        * outside_visible_reflectance
        * mass_area_density
        * area_heat_capacity
    """
    __slots__ = ()

    @property
    def materials(self):
        """Get or set the list of materials in the construction (outside to inside)."""
        return self._materials

    @materials.setter
    def materials(self, mats):
        try:
            if not isinstance(mats, tuple):
                mats = tuple(mats)
        except TypeError:
            raise TypeError('Expected list or tuple for construction materials. '
                            'Got {}'.format(type(mats)))
        for mat in mats:
            assert isinstance(mat, _EnergyMaterialOpaqueBase), 'Expected opaque energy' \
                ' material for construction. Got {}.'.format(type(mat))
        assert len(mats) > 0, 'Construction must possess at least one material.'
        assert len(mats) <= 10, 'Opaque Construction cannot have more than 10 materials.'
        self._materials = mats

    @property
    def inside_emissivity(self):
        """"The emissivity of the inside face of the construction."""
        return self.materials[-1].thermal_absorptance

    @property
    def inside_solar_reflectance(self):
        """"The solar reflectance of the inside face of the construction."""
        return 1 - self.materials[-1].solar_absorptance

    @property
    def inside_visible_reflectance(self):
        """"The visible reflectance of the inside face of the construction."""
        return 1 - self.materials[-1].visible_absorptance

    @property
    def outside_emissivity(self):
        """"The emissivity of the outside face of the construction."""
        return self.materials[0].thermal_absorptance

    @property
    def outside_solar_reflectance(self):
        """"The solar reflectance of the outside face of the construction."""
        return 1 - self.materials[0].solar_absorptance

    @property
    def outside_visible_reflectance(self):
        """"The visible reflectance of the outside face of the construction."""
        return 1 - self.materials[0].visible_absorptance

    @property
    def mass_area_density(self):
        """The area density of the construction [kg/m2]."""
        return sum(tuple(mat.mass_area_density for mat in self.materials))

    @property
    def area_heat_capacity(self):
        """The heat capacity per unit area of the construction [kg/K-m2]."""
        return sum(tuple(mat.area_heat_capacity for mat in self.materials))

    @property
    def thickness(self):
        """Thickness of the construction [m]."""
        thickness = 0
        for mat in self.materials:
            if isinstance(mat, EnergyMaterial):
                thickness += mat.thickness
        return thickness

    def temperature_profile(self, outside_temperature=-18, inside_temperature=21,
                            outside_wind_speed=6.7, height=1.0, angle=90.0,
                            pressure=101325):
        """Get a list of temperatures at each material boundary across the construction.

        Args:
            outside_temperature: The temperature on the outside of the construction [C].
                Default is -18, which is consistent with NFRC 100-2010.
            inside_temperature: The temperature on the inside of the construction [C].
                Default is 21, which is consistent with NFRC 100-2010.
            wind_speed: The average outdoor wind speed [m/s]. This affects outdoor
                convective heat transfer coefficient. Default is 6.7 m/s.
            height: An optional height for the surface in meters. Default is 1.0 m.
            angle: An angle in degrees between 0 and 180.
                0 = A horizontal surface with the outside boundary on the bottom.
                90 = A vertical surface
                180 = A horizontal surface with the outside boundary on the top.
            pressure: The average pressure of in Pa.
                Default is 101325 Pa for standard pressure at sea level.

        Returns:
            temperatures: A list of temperature values [C].
                The first value will always be the outside temperature and the
                second will be the exterior surface temperature.
                The last value will always be the inside temperature and the second
                to last will be the interior surface temperature.
            r_values: A list of R-values for each of the material layers [m2-K/W].
                The first value will always be the resistance of the exterior air
                and the last value is the resistance of the interior air.
                The sum of this list is the R-factor for this construction given
                the input parameters.
        """
        if angle != 90 and outside_temperature > inside_temperature:
            angle = abs(180 - angle)
        in_r_init = 1 / self.in_h_simple()
        r_values = [1 / self.out_h(outside_wind_speed, outside_temperature + 273.15)] + \
            [mat.r_value for mat in self.materials] + [in_r_init]
        in_delta_t = (in_r_init / sum(r_values)) * \
            (outside_temperature - inside_temperature)
        r_values[-1] = 1 / self.in_h(inside_temperature - (in_delta_t / 2) + 273.15,
                                     in_delta_t, height, angle, pressure)
        temperatures = self._temperature_profile_from_r_values(
            r_values, outside_temperature, inside_temperature)
        return temperatures, r_values

    @classmethod
    def from_idf(cls, idf_string, ep_mat_strings):
        """Create an OpaqueConstruction from an EnergyPlus IDF text string.

        Args:
            idf_string: A text string fully describing an EnergyPlus construction.
            ep_mat_strings: A list of text strings for each of the materials in
                the construction.
        """
        materials_dict = cls._idf_materials_dictionary(ep_mat_strings)
        ep_strs = parse_idf_string(idf_string)
        try:
            materials = [materials_dict[mat] for mat in ep_strs[1:]]
        except KeyError as e:
            raise ValueError('Failed to find {} in the input ep_mat_strings.'.format(e))
        return cls(ep_strs[0], materials)

    @classmethod
    def from_standards_dict(cls, data, data_materials):
        """Create an OpaqueConstruction from an OpenStudio standards gem dictionary.

        Args:
            data: An OpenStudio standards dictionary of a Construction in the
                format below.

            .. code-block:: json

                {
                "name": "Typical Insulated Exterior Mass Wall",
                "intended_surface_type": "ExteriorWall",
                "standards_construction_type": "Mass",
                "insulation_layer": "Typical Insulation",
                "materials": [
                    "1IN Stucco",
                    "8IN CONCRETE HW RefBldg",
                    "Typical Insulation",
                    "1/2IN Gypsum"]
                }

            data_materials: Dictionary representation of all materials in the
                OpenStudio standards gem.
        """
        try:
            materials_dict = tuple(data_materials[mat] for mat in data['materials'])
        except KeyError as e:
            raise ValueError('Failed to find {} in OpenStudio Standards material '
                             'library.'.format(e))
        materials = []
        for mat_dict in materials_dict:
            if mat_dict['material_type'] == 'StandardOpaqueMaterial':
                materials.append(EnergyMaterial.from_standards_dict(mat_dict))
            elif mat_dict['material_type'] in ('MasslessOpaqueMaterial', 'AirGap'):
                materials.append(EnergyMaterialNoMass.from_standards_dict(mat_dict))
            else:
                raise NotImplementedError(
                    'Material {} is not supported.'.format(mat_dict['material_type']))
        return cls(data['name'], materials)

    @classmethod
    def from_dict(cls, data):
        """Create a OpaqueConstruction from a dictionary.

        Note that the dictionary must be a non-abridged version for this
        classmethod to work.

        Args:
            data: {
                "type": 'OpaqueConstruction',
                "name": 'Generic Brick Wall',
                "layers": [] // list of material names (from outside to inside)
                "materials": []  // list of unique material objects
                }
        """
        assert data['type'] == 'OpaqueConstruction', \
            'Expected OpaqueConstruction. Got {}.'.format(data['type'])
        materials = {}
        for mat in data['materials']:
            if mat['type'] == 'EnergyMaterial':
                materials[mat['name']] = EnergyMaterial.from_dict(mat)
            elif mat['type'] == 'EnergyMaterialNoMass':
                materials[mat['name']] = EnergyMaterialNoMass.from_dict(mat)
            else:
                raise NotImplementedError(
                    'Material {} is not supported.'.format(mat['type']))
        mat_layers = [materials[mat_name] for mat_name in data['layers']]
        return cls(data['name'], mat_layers)

    def to_idf(self):
        """IDF string representation of construction object.

        Note that this method only outputs a single string for the construction and,
        to write the full construction into an IDF, the construction's unique_materials
        must also be written.

        Returns:
            construction_idf: Text string representation of the construction.
        """
        construction_idf = self._generate_idf_string('opaque', self.name, self.materials)
        return construction_idf

    def to_radiance_solar_interior(self, specularity=0.0):
        """Honeybee Radiance material with the interior solar reflectance."""
        return self.materials[-1].to_radiance_solar(specularity)

    def to_radiance_visible_interior(self, specularity=0.0):
        """Honeybee Radiance material with the interior visible reflectance."""
        return self.materials[-1].to_radiance_visible(specularity)

    def to_radiance_solar_exterior(self, specularity=0.0):
        """Honeybee Radiance material with the exterior solar reflectance."""
        return self.materials[0].to_radiance_solar(specularity)

    def to_radiance_visible_exterior(self, specularity=0.0):
        """Honeybee Radiance material with the exterior visible reflectance."""
        return self.materials[0].to_radiance_visible(specularity)

    def to_dict(self, abridged=False):
        """Opaque construction dictionary representation.

        Args:
            abridged: Boolean to note whether the full dictionary describing the
                object should be returned (False) or just an abridged version (True),
                which only specifies the names of material layers. Default: False.
        """
        base = {'type': 'OpaqueConstruction'} if not \
            abridged else {'type': 'OpaqueConstructionAbridged'}
        base['name'] = self.name
        base['layers'] = self.layers
        if not abridged:
            base['materials'] = [m.to_dict() for m in self.unique_materials]
        return base

    @staticmethod
    def extract_all_from_idf_file(idf_file):
        """Extract all OpaqueConstruction objects from an EnergyPlus IDF file.

        Args:
            idf_file: A path to an IDF file containing objects for opaque
                constructions and corresponding materials.

        Returns:
            constructions: A list of all OpaqueConstruction objects in the IDF
                file as honeybee_energy OpaqueConstruction objects.
            materials: A list of all opaque materials in the IDF file as
                honeybee_energy EnergyMaterial objects.
        """
        # check the file
        assert os.path.isfile(idf_file), 'Cannot find an idf file at {}'.format(idf_file)
        with open(idf_file, 'r') as ep_file:
            file_contents = ep_file.read()
        # extract all of the opaque material objects
        mat_pattern1 = re.compile(r"(?i)(Material,[\s\S]*?;)")
        mat_pattern2 = re.compile(r"(?i)(Material:NoMass,[\s\S]*?;)")
        mat_pattern3 = re.compile(r"(?i)(Material:AirGap,[\s\S]*?;)")
        material_str = mat_pattern1.findall(file_contents) + \
            mat_pattern2.findall(file_contents) + mat_pattern3.findall(file_contents)
        materials_dict = OpaqueConstruction._idf_materials_dictionary(material_str)
        materials = list(materials_dict.values())
        # extract all of the construction objects
        constr_pattern = re.compile(r"(?i)(Construction,[\s\S]*?;)")
        constr_props = tuple(parse_idf_string(idf_string) for
                             idf_string in constr_pattern.findall(file_contents))
        constructions = []
        for constr in constr_props:
            try:
                constr_mats = [materials_dict[mat] for mat in constr[1:]]
                constructions.append(OpaqueConstruction(constr[0], constr_mats))
            except KeyError:
                pass  # the construction is a window construction
        return constructions, materials

    @staticmethod
    def _idf_materials_dictionary(ep_mat_strings):
        """Get a dictionary of opaque EnergyMaterial objects from an IDF string list."""
        materials_dict = {}
        for mat_str in ep_mat_strings:
            mat_str = mat_str.strip()
            if mat_str.startswith('Material:NoMass,'):
                mat_obj = EnergyMaterialNoMass.from_idf(mat_str)
                materials_dict[mat_obj.name] = mat_obj
            elif mat_str.startswith('Material,'):
                mat_obj = EnergyMaterial.from_idf(mat_str)
                materials_dict[mat_obj.name] = mat_obj
        return materials_dict

    def __repr__(self):
        """Represent opaque energy construction."""
        return self._generate_idf_string('opaque', self.name, self.materials)
