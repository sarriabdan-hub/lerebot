package tuc.isse.projekt01.model;

/**
 * Represents a single square on the 7x7 grid.
 * Task D, the container, one box of a Cell.
 * It holds the reference to a Ball and print the pieces itself.
 * @author Haris Masood <haris.masood@tu-clausthal.de>
 * @version 1.0
 *
 *
 */
public class Cell {

    private Ball ball; // Reference to the ball sitting here (null if empty)

    // Constructor: Creates an empty cell
    public Cell() {
        this.ball = null;
    }

    /**
     * Put a ball into this cell
     * @param ball The ball to place in this cell
     */
    public void setBall(Ball ball) {
        this.ball = ball;
    }

    /**
     * Read what ball is here (for game logic)
     * @return The ball in this cell, or null if empty
     */
    public Ball getBall() {
        return this.ball;
    }

    // Task d: Visual Representation
    // Empty -> "[ ]", example if Occupied -> "[X]"
    @Override
    public String toString() {
        if (this.ball == null) {
            return "[ ]"; // Empty cell (Note the space inside)
        } else {
            // We reuse the Ball's own toString() method here!
            return "[" + this.ball.toString() + "]";
        }
    }
}