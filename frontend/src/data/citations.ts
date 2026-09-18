import type { Citation } from '@fasl-work/caos-app-shell';

// Every entry carries a DOI or a URL, each checked against Crossref or the publisher before it was added.
// Ids are authorYYYY[suffix], lowercase.
export const CITATIONS: Citation[] = [
  {
    id: 'berg2026',
    label: 'Berg et al. 2026',
    citation:
      'Berg S, Beckett IR, Costa M, Schlegel P, Januszewski M, and colleagues. Sexual dimorphism in the complete connectome of the Drosophila male central nervous system. Cell, 2026 (preprint: bioRxiv 2025).',
    doi: '10.1101/2025.10.09.680999',
    url: 'https://male-cns.janelia.org/',
  },
  {
    id: 'lappalainen2024',
    label: 'Lappalainen et al. 2024',
    citation:
      'Lappalainen JK, Tschopp FD, Prakhya S, McGill M, Nern A, Shinomiya K, Takemura S, Gruntman E, Macke JH, Turaga SC. Connectome-constrained networks predict neural activity across the fly visual system. Nature, 2024.',
    doi: '10.1038/s41586-024-07939-3',
  },
  {
    id: 'eckstein2024',
    label: 'Eckstein et al. 2024',
    citation:
      'Eckstein N and colleagues. Neurotransmitter classification from electron microscopy images at synaptic sites in Drosophila melanogaster. Cell, 2024.',
    doi: '10.1016/j.cell.2024.03.016',
  },
  {
    id: 'nern2025',
    label: 'Nern et al. 2025',
    citation: 'Nern A and colleagues. Connectome-driven neural inventory of a complete visual system. Nature, 2025.',
    doi: '10.1038/s41586-025-08746-0',
  },
  {
    id: 'takemura2015',
    label: 'Takemura et al. 2015',
    citation:
      'Takemura S and colleagues. Synaptic circuits and their variations within different columns in the visual system of Drosophila. PNAS, 2015.',
    doi: '10.1073/pnas.1509820112',
  },
  {
    id: 'takemura2017',
    label: 'Takemura et al. 2017',
    citation:
      'Takemura S and colleagues. The comprehensive connectome of a neural substrate for ON motion detection in Drosophila. eLife, 2017.',
    doi: '10.7554/eLife.24394',
  },
  {
    id: 'maisak2013',
    label: 'Maisak et al. 2013',
    citation:
      'Maisak MS and colleagues. A directional tuning map of Drosophila elementary motion detectors. Nature, 2013.',
    doi: '10.1038/nature12320',
  },
  {
    id: 'pick2005',
    label: 'Pick and Strauss 2005',
    citation: 'Pick S, Strauss R. Goal-driven behavioral adaptations in gap-climbing Drosophila. Current Biology, 2005.',
    doi: '10.1016/j.cub.2005.07.022',
  },
  {
    id: 'reichardt1983',
    label: 'Reichardt et al. 1983',
    citation:
      'Reichardt W, Poggio T, Hausen K. Figure-ground discrimination by relative movement in the visual system of the fly. Biological Cybernetics, 1983.',
    doi: '10.1007/BF00595226',
  },
  {
    id: 'lukosevicius2009',
    label: 'Lukoševičius and Jaeger 2009',
    citation:
      'Lukoševičius M, Jaeger H. Reservoir computing approaches to recurrent neural network training. Computer Science Review, 2009.',
    doi: '10.1016/j.cosrev.2009.03.005',
  },
  {
    id: 'lehoucq1998',
    label: 'Lehoucq et al. 1998',
    citation:
      'Lehoucq RB, Sorensen DC, Yang C. ARPACK Users’ Guide: solution of large-scale eigenvalue problems with implicitly restarted Arnoldi methods. SIAM, 1998.',
    doi: '10.1137/1.9780898719628',
  },
  {
    id: 'wang2026',
    label: 'Wang and Chen 2026',
    citation: 'Wang B, Chen J. FLYNN: robust neural network for robot navigation using fly brain topology. arXiv, 2026.',
    url: 'https://arxiv.org/abs/2607.00025',
  },
  {
    id: 'flyvis',
    label: 'flyvis',
    citation: 'flyvis: connectome-constrained deep mechanistic networks of the fly visual system (software, MIT).',
    url: 'https://github.com/TuragaLab/flyvis',
  },
  {
    id: 'eigen2014',
    label: 'Eigen et al. 2014',
    citation: 'Eigen D, Puhrsch C, Fergus R. Depth map prediction from a single image using a multi-scale deep network. arXiv, 2014.',
    url: 'https://arxiv.org/abs/1406.2283',
  },
];
