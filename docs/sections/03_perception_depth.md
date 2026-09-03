# 3. Sensing note (depth)

*Folded into the Setup section of the report — kept brief.*

The side RealSense D435i also provides a metric depth stream, recorded alongside
RGB. Because the vials are **transparent glass**, active-stereo depth is unreliable
on them (the sensor tends to see through the glass), so the policy is trained from
the **RGB** streams. Depth is retained in the dataset as a reference channel.
