"""Distinguish rim undercut from contact preload for interference coupons."""
import unittest
import FreeCAD as App
import Part
from joint_holding_trial import withdrawal_overlap,number_label
from joint_retention_trial import ball_key
import freecad_project as authority
from joint_retention_trial import deep_c4


class CaptureTests(unittest.TestCase):
    def test_interference_rim_is_not_rejected_by_net_overlap(self):
        socket=deep_c4({'label':'U10','neck_diameter_mm':2.8,'retention_diameter_mm':5.6,
                        'cavity_clearance_mm':-.300,'label_dots':0})
        seated,net=withdrawal_overlap(socket,3.)
        reference_seated,undercut=withdrawal_overlap(socket,(6.-.300)/2)
        self.assertGreater(seated,.01)
        self.assertLessEqual(net,.01)
        self.assertLess(reference_seated,.01)
        self.assertGreater(undercut,.01)

    def test_both_digits_are_engraved_on_curved_handle(self):
        doc=App.newDocument('NumberTest')
        source=ball_key(2.8,0)
        result=number_label(source,10,authority.PARAMS['joint_workflow_holding_step_trial'],doc,False)
        self.assertTrue(result.isValid())
        self.assertEqual(len(result.Solids),1)
        self.assertEqual(len(source.cut(result).Solids),2)
        App.closeDocument(doc.Name)

    def test_open_hemisphere_has_no_retaining_rim(self):
        shell=Part.makeSphere(5).cut(Part.makeSphere(3))
        shell=shell.common(Part.makeBox(10,20,20,App.Vector(-10,-10,-10)))
        seated,undercut=withdrawal_overlap(shell,3.)
        self.assertLess(seated,.01)
        self.assertLess(undercut,.01)


if __name__=='__main__':unittest.main()
