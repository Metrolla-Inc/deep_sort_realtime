# vim: expandtab:ts=4:sw=4

import numpy as np

class TrackState:
    """
    Enumeration type for the single target track state. Newly created tracks are
    classified as `tentative` until enough evidence has been collected. Then,
    the track state is changed to `confirmed`. Tracks that are no longer alive
    are classified as `deleted` to mark them for removal from the set of active
    tracks.

    """

    Tentative = 1
    Confirmed = 2
    Deleted = 3


class Track:
    """
    A single target track with state space `(x, y, a, h)` and associated
    velocities, where `(x, y)` is the center of the bounding box, `a` is the
    aspect ratio and `h` is the height.

    Parameters
    ----------
    mean : ndarray
        Mean vector of the initial state distribution.
    covariance : ndarray
        Covariance matrix of the initial state distribution.
    track_id : int
        A unique track identifier.
    n_init : int
        Number of consecutive detections before the track is confirmed. The
        track state is set to `Deleted` if a miss occurs within the first
        `n_init` frames.
    max_age : int
        The maximum number of consecutive misses before the track state is
        set to `Deleted`.
    feature : Optional[ndarray]
        Feature vector of the detection this track originates from. If not None,
        this feature is added to the `features` cache.
    original_ltwh : Optional List
        Bounding box associated with matched detection
    det_class : Optional str
        Classname of matched detection
    det_conf : Optional float
        Confidence associated with matched detection
    instance_mask : Optional 
        Instance mask associated with matched detection
    others : Optional any
        Any supplementary fields related to matched detection

    Attributes
    ----------
    mean : ndarray
        Mean vector of the initial state distribution.
    covariance : ndarray
        Covariance matrix of the initial state distribution.
    track_id : int
        A unique track identifier.
    hits : int
        Total number of measurement updates.
    age : int
        Total number of frames since first occurrence.
    time_since_update : int
        Total number of frames since last measurement update.
    state : TrackState
        The current track state.
    features : List[ndarray]
        A cache of features. On each measurement update, the associated feature
        vector is added to this list.

    """

    def __init__(
        self,
        mean,
        covariance,
        track_id,
        n_init,
        max_age,
        feature=None,
        original_ltwh=None,
        det_class=None,
        det_conf=None,
        instance_mask=None,
        others=None,
    ):
        self.mean = mean
        self.covariance = covariance
        self.track_id = track_id
        self.hits = 1
        self.age = 1
        self.time_since_update = 0

        self.state = TrackState.Tentative
        self.features = []
        self.latest_feature = None
        if feature is not None:
            self.features.append(feature)
            self.latest_feature = feature


        self._n_init = n_init
        self._max_age = max_age

        self.original_ltwh = original_ltwh
        self.det_class = det_class
        self.det_conf = det_conf
        self.instance_mask = instance_mask
        self.others = others
        # add a list to append trajectories in
        self.trajectory = []
        # append the current detection center to trajectory
        if original_ltwh is not None:
            self.trajectory.append(self.to_center())

    def to_center(self):
        ret = self.original_ltwh.copy()
        ret[:2] += ret[2:] // 2
        return ret[:2]    

    def to_tlwh(self, orig=False, orig_strict=False):
        """Get current position in bounding box format `(top left x, top left y,
        width, height)`. This function is POORLY NAMED. But we are keeping the way it works the way it works in order not to break any older libraries that depend on this.

        Returns
        -------
        ndarray
            The KF-predicted bounding box by default.
            If `orig` is True and track is matched to a detection this round, then the original det is returned.
        """
        return self.to_ltwh(orig=orig, orig_strict=orig_strict)

    def to_ltwh(self, orig=False, orig_strict=False):
        """Get current position in bounding box format `(top left x, top left y,
        width, height)`.

        Params
        ------
        orig : bool
            To use original detection (True) or KF predicted (False). Only works for original dets that are horizontal BBs.
        orig_strict: bool 
            Only relevant when orig is True. If orig_strict is True, it ONLY outputs original bbs and will not output kalman mean even if original bb is not available. 

        Returns
        -------
        ndarray
            The KF-predicted bounding box by default.
            If `orig` is True and track is matched to a detection this round, then the original det is returned.

        """
        if orig:
            if self.original_ltwh is None:
                if orig_strict:
                    return None
                # else if not orig_strict, return kalman means below
            else:
                return self.original_ltwh.copy()

        ret = self.mean[:4].copy()
        ret[2] *= ret[3]
        ret[:2] -= ret[2:] / 2
        return ret

    def to_tlbr(self, orig=False, orig_strict=False):
        """Get current position in bounding box format `(min x, miny, max x,
        max y)`. This original function is POORLY NAMED. But we are keeping the way it works the way it works in order not to break any older projects that depend on this.
        USE THIS AT YOUR OWN RISK. LIESSSSSSSSSS!
        Returns LIES
        -------
        ndarray
            The KF-predicted bounding box by default.
            If `orig` is True and track is matched to a detection this round, then the original det is returned.
        """
        return self.to_ltrb(orig=orig, orig_strict=orig_strict)

    def to_ltrb(self, orig=False, orig_strict=False):
        """Get current position in bounding box format `(min x, miny, max x,
        max y)`.

        Params
        ------
        orig : bool
            To use original detection (True) or KF predicted (False). Only works for original dets that are horizontal BBs.

        Returns
        -------
        ndarray
            The KF-predicted bounding box by default.
            If `orig` is True and track is matched to a detection this round, then the original det is returned.
        """
        ret = self.to_ltwh(orig=orig, orig_strict=orig_strict)
        if ret is not None:
            ret[2:] = ret[:2] + ret[2:]
        return ret

    def get_det_conf(self):
        """
        `det_conf` will be None is there are no associated detection this round
        """
        return self.det_conf

    def get_det_class(self):
        """
        Only `det_class` will be persisted in the track even if there are no associated detection this round.
        """
        return self.det_class

    def get_instance_mask(self):
        '''
        Get instance mask associated with detection. Will be None is there are no associated detection this round
        '''
        return self.instance_mask
    
    def get_det_supplementary(self):
        """
        Get supplementary info associated with the detection. Will be None is there are no associated detection this round.
        """
        return self.others

    def get_feature(self):
        '''
        Get latest appearance feature
        '''
        return self.latest_feature

    def get_trajectory(self):
        """
        Get trajectory info associated with the track.
        """
        return self.trajectory

    def get_velocity(self, fps=5):
        """
        Get velocity info of the track.
        """
        # If the trajectory only has one element, we cannot get its velocity
        if len(self.trajectory) < 2:
            return None, None, None
        # convert trajectory from list to array
        trajectory_array = np.asarray(self.trajectory)
        # calculate the velocity as discrete different (x[t+1] - x[t]) * fps
        velocity = (trajectory_array[1:] - trajectory_array[:-1]) * fps
        # calculate the velocity magnitude
        velocity_magnitude = np.sqrt(np.sum(velocity ** 2, axis=-1, keepdims=True))
        # calculate the velocity as unit direction vector
        velocity_direction = velocity / (velocity_magnitude + 1e-8)
        # reduce the velocity to the mean velocity
        average_velocity = np.mean(velocity_magnitude)
        # return velocity, velocity magnitude and direction
        return average_velocity, velocity_magnitude, velocity_direction

    def get_trajectory_slope(self):
        """
        Get trajectory slope info of the track.
        """
        # If the trajectory only has one element, we cannot get its velocity
        if len(self.trajectory) < 2:
            return None
        else:
            # convert trajectory from list to array
            trajectory_array = np.asarray(self.trajectory)
            # calculate the difference in y-direction
            diff_y = trajectory_array[-1, 1] - trajectory_array[0, 1]
            # calculate the difference in x-direction with a small value
            # added to avoid division by zero
            diff_x = trajectory_array[-1, 0] - trajectory_array[0, 0] + 1e-07
            # calculate the slope
            slope = diff_y / diff_x
            # return the calculated slope
            return slope

    def predict(self, kf):
        """Propagate the state distribution to the current time step using a
        Kalman filter prediction step.

        Parameters
        ----------
        kf : kalman_filter.KalmanFilter
            The Kalman filter.

        """
        self.mean, self.covariance = kf.predict(self.mean, self.covariance)
        self.age += 1
        self.time_since_update += 1
        self.original_ltwh = None
        self.det_conf = None
        self.instance_mask = None
        self.others = None

    def update(self, kf, detection):
        """Perform Kalman filter measurement update step and update the feature
        cache.

        Parameters
        ----------
        kf : kalman_filter.KalmanFilter
            The Kalman filter.
        detection : Detection
            The associated detection.

        """
        self.original_ltwh = detection.get_ltwh()
        self.mean, self.covariance = kf.update(
            self.mean, self.covariance, detection.to_xyah()
        )
        self.features.append(detection.feature)
        self.latest_feature = detection.feature
        self.det_conf = detection.confidence
        self.det_class = detection.class_name
        self.instance_mask = detection.instance_mask
        self.others = detection.others
        self.trajectory.append(self.to_center())

        self.hits += 1

        self.time_since_update = 0
        if self.state == TrackState.Tentative and self.hits >= self._n_init:
            self.state = TrackState.Confirmed

    def mark_missed(self):
        """Mark this track as missed (no association at the current time step)."""
        if self.state == TrackState.Tentative:
            self.state = TrackState.Deleted
        elif self.time_since_update > self._max_age:
            self.state = TrackState.Deleted

    def is_tentative(self):
        """Returns True if this track is tentative (unconfirmed)."""
        return self.state == TrackState.Tentative

    def is_confirmed(self):
        """Returns True if this track is confirmed."""
        return self.state == TrackState.Confirmed

    def is_deleted(self):
        """Returns True if this track is dead and should be deleted."""
        return self.state == TrackState.Deleted
